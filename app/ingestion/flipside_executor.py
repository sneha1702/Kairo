"""
FlipsideExecutor: submits SQL to the Flipside Data API v2 (JSON-RPC) and returns rows.


Unlike the Dune executor, there is no saved-query concept — every call submits
fresh SQL.  Parameters are rendered into the SQL string before submission, so
the SQL templates use the same {{param}} convention as the Dune queries.

API reference: https://docs.flipsidecrypto.com/flipside-api/get-started
"""

import logging
import re
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api-v2.flipsidecrypto.xyz/json-rpc"

# Flipside terminal query run states
_SUCCESS_STATES = {"QUERY_STATE_SUCCESS", "QUERY_STATE_READY"}
_FAILED_STATES  = {"QUERY_STATE_FAILED", "QUERY_STATE_CANCELED"}


class FlipsideApiError(Exception):
    pass


class FlipsideExecutionError(FlipsideApiError):
    def __init__(self, query_name: str, state: str, detail: str):
        super().__init__(f"[{query_name}] Flipside state={state} — {detail}")
        self.query_name = query_name
        self.state = state


class FlipsideTimeoutError(FlipsideApiError):
    def __init__(self, query_name: str, run_id: str):
        super().__init__(f"[{query_name}] Timed out polling run_id={run_id}")
        self.query_name = query_name
        self.run_id = run_id


class FlipsideExecutor:
    def __init__(
        self,
        api_key: str,
        query_dir: str | Path,
        poll_interval_seconds: int = 5,
        max_polls: int = 120,
        page_size: int = 1000,
    ):
        self.query_dir = Path(query_dir)
        self.poll_interval = poll_interval_seconds
        self.max_polls = max_polls
        self.page_size = page_size

        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": api_key,
            "Content-Type": "application/json",
        })

    # ── Public ──────────────────────────────────────────────────────────────────

    def execute(
        self,
        query_name: str,
        sql_template: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Render *sql_template* with *params*, submit to Flipside, return rows."""
        sql = self._render_sql(sql_template, params)
        run_id = self._submit(query_name, sql)
        logger.info("[%s] Submitted — run_id=%s", query_name, run_id)
        self._wait(run_id, query_name)
        return self._fetch_all(run_id, query_name)

    # ── SQL rendering ────────────────────────────────────────────────────────────

    @staticmethod
    def _render_sql(template: str, params: dict[str, Any]) -> str:
        """Replace {{key}} placeholders with raw param values (no extra quoting)."""
        sql = template
        for key, value in params.items():
            sql = sql.replace(f"{{{{{key}}}}}", str(value))
        # Warn if any placeholders remain unresolved
        unresolved = re.findall(r"\{\{(\w+)\}\}", sql)
        if unresolved:
            logger.warning("Unresolved SQL placeholders: %s", unresolved)
        return sql

    # ── Flipside JSON-RPC ────────────────────────────────────────────────────────

    def _rpc(self, method: str, params: dict | list, query_name: str = "") -> dict:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": [params] if isinstance(params, dict) else params,
            "id": 1,
        }
        resp = self.session.post(BASE_URL, json=payload)
        if not resp.ok:
            raise FlipsideApiError(
                f"[{query_name}] HTTP {resp.status_code} on {method}: {resp.text[:300]}"
            )
        body = resp.json()
        if "error" in body:
            raise FlipsideApiError(
                f"[{query_name}] JSON-RPC error on {method}: {body['error']}"
            )
        return body.get("result", {})

    def _submit(self, query_name: str, sql: str) -> str:
        result = self._rpc(
            "createQueryRun",
            {
                "resultTTLHours": 1,
                "maxAgeMinutes": 0,
                "sql": sql,
                "tags": {"source": "kairo", "query": query_name},
                "dataSource": "snowflake-default",
                "dataProvider": "flipside",
            },
            query_name,
        )
        run_id = result.get("queryRun", {}).get("id", "")
        if not run_id:
            raise FlipsideApiError(f"[{query_name}] No run_id in createQueryRun response")
        return run_id

    def _wait(self, run_id: str, query_name: str) -> None:
        for attempt in range(1, self.max_polls + 1):
            time.sleep(self.poll_interval)
            result = self._rpc("getQueryRun", {"queryRunId": run_id}, query_name)
            state = result.get("queryRun", {}).get("state", "UNKNOWN")
            logger.debug("[%s] Poll %d/%d: state=%s", query_name, attempt, self.max_polls, state)
            if state in _SUCCESS_STATES:
                return
            if state in _FAILED_STATES:
                error_msg = (
                    result.get("queryRun", {}).get("errorMessage", "")
                    or result.get("queryRun", {}).get("error", state)
                )
                raise FlipsideExecutionError(query_name, state, error_msg)
        raise FlipsideTimeoutError(query_name, run_id)

    def _fetch_all(self, run_id: str, query_name: str) -> list[dict[str, Any]]:
        """Fetch paginated results and return as a list of dicts."""
        all_rows: list[dict] = []
        page_num = 1
        while True:
            result = self._rpc(
                "getQueryRunResults",
                {
                    "queryRunId": run_id,
                    "format": "json",
                    "page": {"number": page_num, "size": self.page_size},
                },
                query_name,
            )
            col_labels: list[str] = [c.lower() for c in result.get("columnLabels", [])]
            rows: list[list] = result.get("rows", [])
            page_info: dict = result.get("page", {})

            for row in rows:
                all_rows.append(dict(zip(col_labels, row)))

            total_pages = page_info.get("totalPages", 1)
            if page_num >= total_pages:
                break
            page_num += 1

        logger.info("[%s] Fetched %d rows across %d page(s)", query_name, len(all_rows), page_num)
        return all_rows
