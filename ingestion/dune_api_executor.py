"""
DuneApiExecutor: saves SQL queries to Dune and executes them via the free-tier REST API.

Workflow per query:
  1. On first run: POST /api/v1/query  → stores query_id in query_ids.json
  2. Every run:    POST /api/v1/query/{id}/execute  → get execution_id
  3. Poll:         GET  /api/v1/execution/{exec_id}/results  until COMPLETED

Delete ingestion/query/query_ids.json to force re-creation of all saved queries.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.dune.com/api/v1"

# Parameters whose values are Ethereum addresses → Dune "text" type.
# Everything else is treated as "number".
_TEXT_PARAMS = {"token_address"}


class DuneApiError(Exception):
    pass


class DuneExecutionError(DuneApiError):
    def __init__(self, query_name: str, state: str, raw: str):
        super().__init__(f"[{query_name}] Dune state={state}")
        self.query_name = query_name
        self.state = state
        self.raw = raw


class DuneTimeoutError(DuneApiError):
    def __init__(self, query_name: str, execution_id: str):
        super().__init__(f"[{query_name}] Timed out polling execution_id={execution_id}")
        self.query_name = query_name
        self.execution_id = execution_id


class DuneApiExecutor:
    def __init__(
        self,
        api_key: str,
        query_dir: str | Path,
        poll_interval_seconds: int = 5,
        max_polls: int = 60,
    ):
        self.query_dir = Path(query_dir)
        self.poll_interval = poll_interval_seconds
        self.max_polls = max_polls
        self._ids_path = self.query_dir / "query_ids.json"
        self._query_ids: dict[str, int] = self._load_ids()

        self.session = requests.Session()
        self.session.headers.update({
            "x-dune-api-key": api_key,
            "Content-Type": "application/json",
        })

    # ── Public ──────────────────────────────────────────────────────────────────

    def execute(
        self,
        query_name: str,
        sql: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Ensure query exists in Dune, execute it, and return rows."""
        query_id = self._ensure_query(query_name, sql, params)
        execution_id = self._submit(query_id, query_name, params)
        logger.info("[%s] Executing query_id=%d  execution_id=%s", query_name, query_id, execution_id)
        return self._poll(execution_id, query_name)

    # ── Query registry ───────────────────────────────────────────────────────────

    def _load_ids(self) -> dict[str, int]:
        if self._ids_path.exists():
            try:
                return json.loads(self._ids_path.read_text())
            except Exception:
                return {}
        return {}

    def _save_ids(self) -> None:
        self._ids_path.write_text(json.dumps(self._query_ids, indent=2))

    # ── Dune API calls ───────────────────────────────────────────────────────────

    def _ensure_query(self, query_name: str, sql: str, params: dict[str, Any]) -> int:
        if query_name in self._query_ids:
            qid = self._query_ids[query_name]
            logger.debug("[%s] Using cached query_id=%d", query_name, qid)
            return qid
        return self._create_query(query_name, sql, params)

    def _create_query(self, query_name: str, sql: str, params: dict[str, Any]) -> int:
        used_keys = set(re.findall(r"\{\{(\w+)\}\}", sql))
        payload = {
            "name": f"kairo__{query_name}",
            "query_sql": sql,
            "parameters": self._build_param_schema(params, used_keys),
            "is_private": False,
        }
        resp = self.session.post(f"{BASE_URL}/query", json=payload)
        self._raise_for_status(resp, query_name, "create query")
        query_id: int = resp.json()["query_id"]
        logger.info("[%s] Created Dune query query_id=%d", query_name, query_id)
        self._query_ids[query_name] = query_id
        self._save_ids()
        return query_id

    def _submit(self, query_id: int, query_name: str, params: dict[str, Any]) -> str:
        sql = (self.query_dir / f"{query_name}.sql").read_text()
        used_keys = set(re.findall(r"\{\{(\w+)\}\}", sql))
        # REST API expects query_parameters as a flat {key: value} dict.
        payload: dict[str, Any] = {
            "query_parameters": {k: v for k, v in params.items() if k in used_keys},
        }
        resp = self.session.post(f"{BASE_URL}/query/{query_id}/execute", json=payload)
        if resp.status_code == 404:
            # Query was deleted from Dune — remove cached ID and recreate
            logger.warning("[%s] query_id=%d not found, recreating", query_name, query_id)
            del self._query_ids[query_name]
            self._save_ids()
            sql_text = (self.query_dir / f"{query_name}.sql").read_text()
            new_id = self._create_query(query_name, sql_text, params)
            resp = self.session.post(f"{BASE_URL}/query/{new_id}/execute", json=payload)
        self._raise_for_status(resp, query_name, "execute query")
        return resp.json()["execution_id"]

    def _poll(self, execution_id: str, query_name: str) -> list[dict[str, Any]]:
        url = f"{BASE_URL}/execution/{execution_id}/results"
        for attempt in range(1, self.max_polls + 1):
            time.sleep(self.poll_interval)
            resp = self.session.get(url)
            self._raise_for_status(resp, query_name, f"poll attempt {attempt}")
            data = resp.json()
            state = data.get("state", "UNKNOWN")
            logger.debug("[%s] Poll %d/%d: state=%s", query_name, attempt, self.max_polls, state)
            if state == "QUERY_STATE_COMPLETED":
                rows = data.get("result", {}).get("rows", [])
                logger.info("[%s] Completed — %d rows", query_name, len(rows))
                return rows
            if state == "QUERY_STATE_FAILED":
                raise DuneExecutionError(query_name, state, str(data))
        raise DuneTimeoutError(query_name, execution_id)

    # ── Parameter helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _param_type(key: str, value: Any) -> str:
        if key in _TEXT_PARAMS or isinstance(value, str):
            return "text"
        return "number"

    def _build_param_schema(
        self, params: dict[str, Any], used_keys: set[str]
    ) -> list[dict]:
        return [
            {
                "key": k,
                "type": self._param_type(k, v),
                "value": str(v),
            }
            for k, v in params.items()
            if k in used_keys
        ]

    # ── Error handling ───────────────────────────────────────────────────────────

    @staticmethod
    def _raise_for_status(resp: requests.Response, query_name: str, op: str) -> None:
        if not resp.ok:
            body = resp.text[:400]
            raise DuneApiError(
                f"[{query_name}] Dune API error during {op}: "
                f"HTTP {resp.status_code} — {body}"
            )
