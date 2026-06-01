"""
DuneApiExecutor: saves SQL queries to Dune and executes them via the free-tier REST API.

Workflow per query:
  1. On first run: POST /api/v1/query  → stores query_id + sql_hash in query_ids.json
  2. On SQL change: PATCH /api/v1/query/{id} → updates query in Dune, refreshes stored hash
  3. Every run:    POST /api/v1/query/{id}/execute  → get execution_id
  4. Poll:         GET  /api/v1/execution/{exec_id}/results  until COMPLETED

Delete ingestion/query/query_ids.json to force re-creation of all saved queries.

query_ids.json format (v2):
  {"query_name": {"id": 12345, "sql_hash": "abcd1234"}}
Old plain-int format is migrated automatically on first load.
"""

import hashlib
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
        self._query_ids: dict[str, dict] = self._load_ids()

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
        """Ensure query exists in Dune (and is up-to-date), execute it, return rows."""
        query_id = self._ensure_query(query_name, sql, params)
        execution_id = self._submit(query_id, query_name, params)
        logger.info("[%s] Executing query_id=%d  execution_id=%s", query_name, query_id, execution_id)
        return self._poll(execution_id, query_name)

    # ── Query registry ───────────────────────────────────────────────────────────

    def _load_ids(self) -> dict[str, dict]:
        """Load query_ids.json, migrating the old plain-int format to {id, sql_hash}."""
        if not self._ids_path.exists():
            return {}
        try:
            raw: dict = json.loads(self._ids_path.read_text())
        except Exception:
            return {}
        result: dict[str, dict] = {}
        for k, v in raw.items():
            if isinstance(v, int):
                # Old format — migrate; empty hash forces an update on next run
                result[k] = {"id": v, "sql_hash": ""}
            elif isinstance(v, dict) and "id" in v:
                result[k] = v
        return result

    def _save_ids(self) -> None:
        self._ids_path.write_text(json.dumps(self._query_ids, indent=2))

    @staticmethod
    def _sql_hash(sql: str) -> str:
        return hashlib.sha256(sql.encode()).hexdigest()[:16]

    # ── Dune API calls ───────────────────────────────────────────────────────────

    def _ensure_query(self, query_name: str, sql: str, params: dict[str, Any]) -> int:
        current_hash = self._sql_hash(sql)

        if query_name in self._query_ids:
            entry = self._query_ids[query_name]
            qid = entry["id"]
            if entry.get("sql_hash") != current_hash:
                logger.info(
                    "[%s] SQL changed — patching query_id=%d in Dune", query_name, qid
                )
                self._patch_query(query_name, qid, sql, params)
                entry["sql_hash"] = current_hash
                self._save_ids()
            else:
                logger.debug("[%s] SQL unchanged — reusing query_id=%d", query_name, qid)
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
        self._query_ids[query_name] = {"id": query_id, "sql_hash": self._sql_hash(sql)}
        self._save_ids()
        return query_id

    def _patch_query(self, query_name: str, query_id: int, sql: str, params: dict[str, Any]) -> None:
        """Update an existing Dune query with new SQL via PATCH."""
        used_keys = set(re.findall(r"\{\{(\w+)\}\}", sql))
        payload = {
            "query_sql": sql,
            "parameters": self._build_param_schema(params, used_keys),
        }
        resp = self.session.patch(f"{BASE_URL}/query/{query_id}", json=payload)
        if resp.status_code == 404:
            # Query was deleted from Dune — remove entry and recreate
            logger.warning("[%s] query_id=%d not found on PATCH, recreating", query_name, query_id)
            del self._query_ids[query_name]
            self._save_ids()
            self._create_query(query_name, sql, params)
            return
        self._raise_for_status(resp, query_name, "patch query")
        logger.info("[%s] Patched Dune query_id=%d", query_name, query_id)

    def _submit(self, query_id: int, query_name: str, params: dict[str, Any]) -> str:
        sql = (self.query_dir / f"{query_name}.sql").read_text()
        used_keys = set(re.findall(r"\{\{(\w+)\}\}", sql))
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
