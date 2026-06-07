"""
DuneIngestionPipeline: saves SQL queries to Dune and bulk-indexes results into
dedicated Elasticsearch indices via the Dune free-tier REST API.

CLI usage:
  python dune_pipeline.py                              # run all 12 queries
  python dune_pipeline.py --queries whale_transaction_filter volume_spike_detection
  python dune_pipeline.py --cadence 6                  # only 6h-cadence queries
  python dune_pipeline.py --dry-run                    # print SQL, skip execution
"""

import argparse
import hashlib
import logging
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import os

# ── .env loading (optional) ────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure repo root is on PYTHONPATH for direct script execution
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


import yaml
from elasticsearch import Elasticsearch
from elasticsearch import helpers as es_helpers

from config.config import Config
from app.ingestion.base_pipeline import (
    BaseIngestionPipeline,
    QUERY_TO_INDEX,
    QUERY_TO_SIGNAL,
    CADENCE_GROUPS,
    QueryConfig,
    IngestionResult,
)
from app.ingestion.dune_index_manager import DuneIndexManager
from app.brain.elasticsearch_manager import ElasticsearchManager
from app.ingestion.dune_api_executor import DuneApiExecutor, DuneApiError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ── Pipeline ───────────────────────────────────────────────────────────────────

class DuneIngestionPipeline(BaseIngestionPipeline):
    def __init__(
        self,
        es_client: Elasticsearch,
        dune_executor: DuneApiExecutor,
        query_dir: Path,
        config_path: Path,
    ):
        self.es = es_client
        self.dune = dune_executor
        self.query_dir = query_dir
        self.config_path = config_path
        self._raw_config: dict | None = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def run_all(
        self,
        query_names: list[str] | None = None,
        dry_run: bool = False,
        end_time: str | None = None,
        time_window_hours: int | None = None,
    ) -> dict[str, IngestionResult]:
        configs = self._load_query_configs(query_names, end_time=end_time, time_window_hours=time_window_hours)
        results: dict[str, IngestionResult] = {}

        with ThreadPoolExecutor(max_workers=3) as pool:  # free tier: max 3 concurrent executions
            futures = {pool.submit(self.run_one, qc, dry_run): qc for qc in configs}
            for future in as_completed(futures):
                qc = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = IngestionResult(query_name=qc.query_name, error=exc)
                results[qc.query_name] = result
                _log_result(result)

        return results

    def run_one(self, qc: QueryConfig, dry_run: bool = False) -> IngestionResult:
        start = time.monotonic()
        result = IngestionResult(query_name=qc.query_name)
        try:
            sql = qc.sql_path.read_text()

            if dry_run:
                logger.info("[%s] DRY RUN — SQL (%d chars)", qc.query_name, len(sql))
                logger.info(sql[:500] + ("..." if len(sql) > 500 else ""))
                result.success = True
                return result

            rows = self.dune.execute(qc.query_name, sql, qc.params)
            result.rows_fetched = len(rows)

            ingested_at = datetime.now(timezone.utc)
            docs = self._add_metadata_envelope(rows, qc, ingested_at)
            for doc in docs:
                doc["_id"] = self._make_doc_id(qc, doc, ingested_at)

            ok, failed = self._bulk_index(docs, qc.target_index)
            result.docs_indexed = ok
            result.docs_failed = len(failed)
            result.failed_docs = failed
            result.success = True

        except Exception as exc:
            result.error = exc
            logger.error("[%s] Error: %s", qc.query_name, exc)
        finally:
            result.duration_seconds = round(time.monotonic() - start, 2)
        return result

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _load_query_configs(
        self,
        query_names: list[str] | None,
        end_time: str | None = None,
        time_window_hours: int | None = None,
    ) -> list[QueryConfig]:
        if self._raw_config is None:
            with open(self.config_path) as f:
                self._raw_config = yaml.safe_load(f)

        cfg = self._raw_config or {}
        globals_ = cfg.get("globals") or {}
        queries_cfg = cfg.get("queries") or {}
        names = query_names or list(QUERY_TO_INDEX.keys())

        # Precedence: caller override > Config value > YAML globals fallback.
        effective_global_hours = time_window_hours if time_window_hours is not None else Config.DUNE_QUERY_WINDOW_HOURS
        # end_time defaults to now (UTC) so regular runs behave identically to before.
        effective_end_time = end_time or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        result = []
        for name in names:
            per_query = queries_cfg.get(name, {})
            # Inject end_time and time_window_hours before per-query overrides so that
            # per-query YAML can still override time_window_hours for special cases,
            # but end_time is always set (backfill callers override it per chunk).
            params = {
                **globals_,
                "time_window_hours": effective_global_hours,
                "end_time": effective_end_time,
                **per_query,
            }
            # Per-query time_window_hours override must not clobber a backfill end_time
            if end_time is not None:
                params["end_time"] = end_time
                params["time_window_hours"] = time_window_hours if time_window_hours is not None else int(params.get("time_window_hours", effective_global_hours))
            cadence = int(params.get("time_window_hours", effective_global_hours))
            result.append(QueryConfig(
                query_name=name,
                sql_path=self.query_dir / f"{name}.sql",
                params=params,
                cadence_hours=cadence,
                signal_category=QUERY_TO_SIGNAL[name],
                target_index=QUERY_TO_INDEX[name],
            ))
        return result

    # Dune returns timestamps as "2026-05-30 11:32:23.000 UTC" or "2026-04-19 00:00:00";
    # ES date fields require ISO 8601 (T separator, optional Z suffix).
    _DUNE_TS_UTC = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}(?:\.\d+)?) UTC$")
    _DUNE_TS_BARE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}(?:\.\d+)?)$")

    def _normalize_doc(self, doc: dict) -> dict:
        for k, v in list(doc.items()):
            if isinstance(v, str):
                m = self._DUNE_TS_UTC.match(v)
                if m:
                    doc[k] = f"{m.group(1)}T{m.group(2)}Z"
                    continue
                m = self._DUNE_TS_BARE.match(v)
                if m:
                    doc[k] = f"{m.group(1)}T{m.group(2)}"
            # Arrays (e.g. signals) and other non-string types pass through unchanged.
        return doc

    @staticmethod
    def _resolve_end_dt(qc: QueryConfig, ingested_at: datetime) -> datetime:
        """Return the logical end of the data window (end_time param or ingested_at)."""
        raw = qc.params.get("end_time")
        if raw:
            try:
                dt = datetime.fromisoformat(raw)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return ingested_at

    def _add_metadata_envelope(
        self,
        rows: list[dict],
        qc: QueryConfig,
        ingested_at: datetime,
    ) -> list[dict]:
        end_dt = self._resolve_end_dt(qc, ingested_at)
        tw = qc.params.get("time_window_hours")
        window_start = (
            (end_dt - timedelta(hours=int(tw))).isoformat()
            if tw is not None
            else None
        )
        # Only inject token_address for the two queries whose ES mappings include it
        _TOKEN_ADDRESS_QUERIES = {"wallet_concentration", "new_holder_growth"}
        token_address = qc.params.get("token_address")
        enriched = []
        for row in rows:
            doc = self._normalize_doc(dict(row))
            doc["ingested_at"]        = ingested_at.isoformat()
            doc["query_name"]         = qc.query_name
            doc["signal_category"]    = qc.signal_category
            doc["time_window_hours"]  = int(tw) if tw is not None else None
            doc["window_start"]       = window_start
            doc["params_snapshot"]    = dict(qc.params)
            if token_address and "token_address" not in doc and qc.query_name in _TOKEN_ADDRESS_QUERIES:
                doc["token_address"] = token_address
            enriched.append(doc)
        return enriched

    def _make_doc_id(
        self, qc: QueryConfig, doc: dict, ingested_at: datetime
    ) -> str:
        name = qc.query_name
        # Use end_time param (deterministic across re-runs of same chunk) or ingested_at.
        end_dt = self._resolve_end_dt(qc, ingested_at)
        tw = qc.params.get("time_window_hours")
        if tw is not None:
            ws = (end_dt - timedelta(hours=int(tw))).replace(
                minute=0, second=0, microsecond=0
            ).isoformat()
        else:
            ws = end_dt.strftime("%Y-%m-%d")

        if name == "whale_transaction_filter":
            parts = [str(doc.get("tx_hash", ""))]
        elif name == "smart_money_accumulation":
            # Now one row per symbol (restructured from per-wallet)
            parts = [str(doc.get("symbol", "")), ws]
        elif name == "token_inflow_outflow":
            # token column renamed to symbol
            parts = [str(doc.get("symbol", "")), ws]
        elif name == "bridge_activity":
            # direction replaced by symbol + from_chain + to_chain + bridge_name
            parts = [
                str(doc.get("symbol", "")),
                str(doc.get("from_chain", "")),
                str(doc.get("to_chain", "")),
                str(doc.get("bridge_name", "")),
                ws,
            ]
        elif name == "wallet_concentration":
            parts = [str(qc.params.get("token_address", "")), str(doc.get("address", "")), ws]
        elif name == "volume_spike_detection":
            parts = [str(doc.get("symbol", "")), ws]
        elif name == "new_holder_growth":
            parts = [str(qc.params.get("token_address", "")), ws]
        elif name == "dex_trading_concentration":
            parts = [str(doc.get("symbol", "")), str(doc.get("dex", "")), ws]
        elif name == "post_bridge_deployment":
            parts = [
                str(doc.get("symbol", "")),
                str(doc.get("chain", "")),
                str(doc.get("deployment_type", "")),
                str(doc.get("protocol", "")),
                ws,
            ]
        elif name == "stablecoin_liquidity_flow":
            parts = [str(doc.get("symbol", "")), ws]
        elif name == "ecosystem_sector_rotation":
            parts = [str(doc.get("symbol", "")), ws]
        elif name == "protocol_inflow_leaderboard":
            parts = [
                str(doc.get("symbol", "")),
                str(doc.get("deployment_type", "")),
                ws,
            ]
        else:
            parts = [name, ws]

        return hashlib.sha256("||".join(parts).encode()).hexdigest()[:24]

    def _bulk_index(
        self, docs: list[dict], index: str
    ) -> tuple[int, list[dict]]:
        actions = [
            {
                "_index": index,
                "_id": doc.pop("_id"),
                "_source": doc,
            }
            for doc in docs
        ]
        result = es_helpers.bulk(self.es, actions, raise_on_error=False)
        if isinstance(result, tuple):
            ok, errors = result
        else:
            ok, errors = result, []

        # Ensure errors is a list of error items. Some clients may return
        # unexpected types (e.g. an int); normalize to a list for the
        # function's declared return type and downstream handling.
        if not isinstance(errors, (list, tuple)):
            errors = []
        else:
            errors = list(errors)

        if errors:
            for err in errors:
                logger.error("Bulk index error in %s: %s", index, err)

        return ok, errors

    def purge_old_documents(self, days: int = 7) -> None:
        """Delete documents older than `days` from all dune_* indices."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        for index in QUERY_TO_INDEX.values():
            try:
                resp = self.es.delete_by_query(
                    index=index,
                    body={"query": {"range": {"ingested_at": {"lt": cutoff}}}},
                    conflicts="proceed",
                )
                deleted = resp.get("deleted", 0)
                if deleted:
                    logger.info("Purged %d docs older than %dd from %s", deleted, days, index)
            except Exception as exc:
                logger.warning("Could not purge %s: %s", index, exc)


# ── Logging helper ─────────────────────────────────────────────────────────────

def _log_result(r: IngestionResult) -> None:
    if r.success:
        logger.info(
            "[%s] OK  rows=%d indexed=%d failed=%d  (%.1fs)",
            r.query_name, r.rows_fetched, r.docs_indexed, r.docs_failed, r.duration_seconds,
        )
    else:
        logger.error(
            "[%s] FAIL  error=%s  (%.1fs)",
            r.query_name, r.error, r.duration_seconds,
        )


# ── Factory ────────────────────────────────────────────────────────────────────

def build_pipeline() -> DuneIngestionPipeline:
    if not Config.DUNE_API_KEY:
        raise ValueError("DUNE_API_KEY is not set — export it or add it to .env")

    es_manager = ElasticsearchManager(
        Config.ES_URL,
        Config.ES_USERNAME,
        Config.ES_PASSWORD,
        Config.ES_API_KEY_ID,
    )
    es_client = es_manager.get_client()

    index_manager = DuneIndexManager(es_client)
    index_manager.ensure_all_indices()

    dune = DuneApiExecutor(
        api_key=Config.DUNE_API_KEY,
        query_dir=Config.QUERY_DIR,
    )

    return DuneIngestionPipeline(
        es_client=es_client,
        dune_executor=dune,
        query_dir=Path(Config.QUERY_DIR),
        config_path=Path(Config.QUERY_DIR) / "config.yaml",
    )


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Dune → Elasticsearch ingestion")
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--queries", nargs="+", choices=list(QUERY_TO_INDEX.keys()),
        metavar="QUERY", help="Run specific queries by name",
    )
    group.add_argument(
        "--cadence", type=int, choices=[6, 24],
        help="Run only queries for this cadence group (6 or 24 hours)",
    )
    p.add_argument("--dry-run", action="store_true", help="Resolve SQL but skip Tempo execution")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.cadence:
        query_names = CADENCE_GROUPS[args.cadence]
    else:
        query_names = args.queries  # None = all

    pipeline = build_pipeline()
    results = pipeline.run_all(query_names=query_names, dry_run=args.dry_run)

    failed = [r for r in results.values() if not r.success]
    if failed:
        import sys
        logger.error("%d queries failed: %s", len(failed), [r.query_name for r in failed])
        sys.exit(1)
    logger.info("All queries completed successfully.")
