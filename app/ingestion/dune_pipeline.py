"""
DuneIngestionPipeline: saves SQL queries to Dune and bulk-indexes results into
dedicated Elasticsearch indices via the Dune free-tier REST API.

CLI usage:
  python dune_pipeline.py                              # run all 8 queries
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

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

import yaml
from elasticsearch import Elasticsearch
from elasticsearch import helpers as es_helpers

from config.config import Config
from app.ingestion.dune_index_manager import DuneIndexManager
from app.brain.elasticsearch_manager import ElasticsearchManager
from app.ingestion.dune_api_executor import DuneApiExecutor, DuneApiError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

QUERY_TO_INDEX: dict[str, str] = {
    "whale_transaction_filter":  "dune_whale_transactions",
    "smart_money_accumulation":  "dune_smart_money",
    "token_inflow_outflow":      "dune_token_flows",
    "bridge_activity":           "dune_bridge_activity",
    "wallet_concentration":      "dune_wallet_concentration",
    "volume_spike_detection":    "dune_volume_spikes",
    "new_holder_growth":         "dune_holder_growth",
    "dex_trading_concentration": "dune_dex_concentration",
}

QUERY_TO_SIGNAL: dict[str, str] = {
    "whale_transaction_filter":  "WHALE_FLOW",
    "smart_money_accumulation":  "SMART_MONEY",
    "token_inflow_outflow":      "TOKEN_FLOW",
    "bridge_activity":           "BRIDGE",
    "wallet_concentration":      "CONCENTRATION",
    "volume_spike_detection":    "VOLUME_SPIKE",
    "new_holder_growth":         "HOLDER_GROWTH",
    "dex_trading_concentration": "DEX_LIQUIDITY",
}

CADENCE_GROUPS: dict[int, list[str]] = {
    6:  ["whale_transaction_filter", "smart_money_accumulation",
         "volume_spike_detection", "dex_trading_concentration"],
    24: ["token_inflow_outflow", "bridge_activity",
         "new_holder_growth", "wallet_concentration"],
}


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class QueryConfig:
    query_name: str
    sql_path: Path
    params: dict[str, Any]
    cadence_hours: int
    signal_category: str
    target_index: str


@dataclass
class IngestionResult:
    query_name: str
    success: bool = False
    rows_fetched: int = 0
    docs_indexed: int = 0
    docs_failed: int = 0
    failed_docs: list[dict] = field(default_factory=list)
    error: Exception | None = None
    duration_seconds: float = 0.0


# ── Pipeline ───────────────────────────────────────────────────────────────────

class DuneIngestionPipeline:
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
    ) -> dict[str, IngestionResult]:
        configs = self._load_query_configs(query_names)
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

    def _load_query_configs(self, query_names: list[str] | None) -> list[QueryConfig]:
        if self._raw_config is None:
            with open(self.config_path) as f:
                self._raw_config = yaml.safe_load(f)

        cfg = self._raw_config or {}
        globals_ = cfg.get("globals") or {}
        queries = cfg.get("queries") or {}
        names = query_names or list(QUERY_TO_INDEX.keys())
        result = []
        for name in names:
            params = {**globals_, **queries.get(name, {})}
            cadence = int(params.get("time_window_hours", 24))
            result.append(QueryConfig(
                query_name=name,
                sql_path=self.query_dir / f"{name}.sql",
                params=params,
                cadence_hours=cadence,
                signal_category=QUERY_TO_SIGNAL[name],
                target_index=QUERY_TO_INDEX[name],
            ))
        return result

    # Dune returns timestamps as "2026-05-30 11:32:23.000 UTC"; ES requires ISO 8601.
    _DUNE_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}(?:\.\d+)?) UTC$")

    def _normalize_doc(self, doc: dict) -> dict:
        for k, v in doc.items():
            if isinstance(v, str):
                m = self._DUNE_TS.match(v)
                if m:
                    doc[k] = f"{m.group(1)}T{m.group(2)}Z"
        return doc

    def _add_metadata_envelope(
        self,
        rows: list[dict],
        qc: QueryConfig,
        ingested_at: datetime,
    ) -> list[dict]:
        tw = qc.params.get("time_window_hours")
        window_start = (
            (ingested_at - timedelta(hours=int(tw))).isoformat()
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
        # window_start truncated to the hour
        tw = qc.params.get("time_window_hours")
        if tw is not None:
            ws = (ingested_at - timedelta(hours=int(tw))).replace(
                minute=0, second=0, microsecond=0
            ).isoformat()
        else:
            ws = ingested_at.strftime("%Y-%m-%d")

        if name == "whale_transaction_filter":
            parts = [str(doc.get("tx_hash", ""))]
        elif name == "smart_money_accumulation":
            parts = [str(doc.get("wallet", "")), str(doc.get("symbol", "")), ws]
        elif name == "token_inflow_outflow":
            parts = [str(doc.get("token", "")), ws]
        elif name == "bridge_activity":
            parts = [str(doc.get("direction", "")), str(doc.get("bridge", "")), ws]
        elif name == "wallet_concentration":
            parts = [str(qc.params.get("token_address", "")), str(doc.get("address", "")), ws]
        elif name == "volume_spike_detection":
            parts = [str(doc.get("symbol", "")), ws]
        elif name == "new_holder_growth":
            parts = [str(qc.params.get("token_address", "")),
                     str(doc.get("view_type", "")), ws]
        elif name == "dex_trading_concentration":
            parts = [str(doc.get("symbol", "")), str(doc.get("dex", "")), ws]
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
