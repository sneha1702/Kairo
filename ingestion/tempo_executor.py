"""
TempoExecutor: wraps Tempo MPP subprocess for Dune SQL execution.
Ports run_query.sh logic to Python for typed exceptions and testability.
"""

import json
import logging
import subprocess
import time
from typing import Any

logger = logging.getLogger(__name__)

PAYMENT_KEYWORDS = ("payment", "credits", "insufficient", "deposit", "E_PAYMENT")


class TempoError(Exception):
    pass


class TempoPaymentError(TempoError):
    """Tempo wallet has insufficient credits."""
    pass


class TempoExecutionError(TempoError):
    """Dune returned QUERY_STATE_FAILED."""
    def __init__(self, query_name: str, state: str, raw: str):
        super().__init__(f"[{query_name}] Dune state={state}")
        self.query_name = query_name
        self.state = state
        self.raw = raw


class TempoTimeoutError(TempoError):
    """Polling exceeded max_polls without completion."""
    def __init__(self, query_name: str, execution_id: str):
        super().__init__(f"[{query_name}] Timed out polling execution_id={execution_id}")
        self.query_name = query_name
        self.execution_id = execution_id


class TempoExecutor:
    def __init__(
        self,
        tempo_bin: str,
        dune_base_url: str = "https://api.dune.com",
        poll_interval_seconds: int = 3,
        max_polls: int = 40,
    ):
        self.tempo_bin = tempo_bin
        self.dune_base_url = dune_base_url.rstrip("/")
        self.poll_interval = poll_interval_seconds
        self.max_polls = max_polls

    def execute(self, sql: str, query_name: str = "query") -> list[dict[str, Any]]:
        """Submit SQL to Dune via Tempo MPP, poll until done, return rows."""
        execution_id = self._submit(sql, query_name)
        logger.info("[%s] Submitted — execution_id=%s", query_name, execution_id)
        return self._poll(execution_id, query_name)

    def _submit(self, sql: str, query_name: str) -> str:
        payload = json.dumps({"query_sql": sql})
        result = self._run_tempo(
            "request", "-t", "-X", "POST", "--json", payload,
            f"{self.dune_base_url}/api/v1/sql/execute",
        )
        self._check_payment_error(result, query_name)
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            raise TempoError(f"[{query_name}] Non-JSON submit response: {result[:300]}")
        execution_id = data.get("execution_id", "")
        if not execution_id:
            # Check again for payment errors embedded in parsed response
            msg = str(data)
            if any(k in msg.lower() for k in PAYMENT_KEYWORDS):
                raise TempoPaymentError(f"[{query_name}] Payment error: {msg[:300]}")
            raise TempoError(f"[{query_name}] No execution_id in response: {result[:300]}")
        return execution_id

    def _poll(self, execution_id: str, query_name: str) -> list[dict[str, Any]]:
        url = f"{self.dune_base_url}/api/v1/execution/{execution_id}/results"
        for attempt in range(1, self.max_polls + 1):
            time.sleep(self.poll_interval)
            raw = self._run_tempo("request", "-t", url)
            self._check_payment_error(raw, query_name)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("[%s] Poll %d: non-JSON response", query_name, attempt)
                continue
            state = data.get("state", "UNKNOWN")
            logger.debug("[%s] Poll %d: state=%s", query_name, attempt, state)
            if state == "QUERY_STATE_COMPLETED":
                rows = data.get("result", {}).get("rows", [])
                logger.info("[%s] Completed — %d rows", query_name, len(rows))
                return rows
            if state == "QUERY_STATE_FAILED":
                raise TempoExecutionError(query_name, state, raw)
        raise TempoTimeoutError(query_name, execution_id)

    def _run_tempo(self, *args: str) -> str:
        cmd = [self.tempo_bin, *args]
        timeout = self.max_polls * self.poll_interval + 30
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise TempoError(f"Tempo subprocess timed out after {timeout}s")
        if proc.stderr and proc.stderr.strip():
            logger.debug("Tempo stderr: %s", proc.stderr.strip())
        return (proc.stdout or "").strip()

    def _check_payment_error(self, raw: str, query_name: str) -> None:
        if any(k in raw for k in PAYMENT_KEYWORDS):
            raise TempoPaymentError(f"[{query_name}] Payment error: {raw[:300]}")
