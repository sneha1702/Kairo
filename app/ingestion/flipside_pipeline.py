"""
FlipsideIngestionPipeline: runs the same 12 on-chain signal queries against the
Flipside Data API and indexes results into the same Elasticsearch indices as the
Dune pipeline.

SQL templates live in app/ingestion/flipside_query/ and use the same {{param}}
convention, but target Snowflake (Flipside) table names.  Parameters are
rendered client-side before submission — no saved query IDs are needed.
"""

import hashlib
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from elasticsearch import Elasticsearch
from elasticsearch import helpers as es_helpers

from config.config import Config
from app.ingestion.base_pipeline import (
    BaseIngestionPipeline,
    QUERY_TO_INDEX,
    QUERY_TO_SIGNAL,
    QueryConfig,
    IngestionResult,
)
from app.ingestion.flipside_executor import FlipsideExecutor, FlipsideApiError
from app.ingestion.dune_index_manager import DuneIndexManager
from app.brain.elasticsearch_manager import ElasticsearchManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Queries that Flipside cannot serve (no CEX-flow data equivalent)
FLIPSIDE_UNSUPPORTED: set[str] = set()


class FlipsideIngestionPipeline(BaseIngestionPipeline):
    provider_name = "flipside"

    def __init__(
        self,
        es_client: Elasticsearch,
        flipside_executor: FlipsideExecutor,
        query_dir: Path,
        config_path: Path,
    ):
        self.es = es_client
        self.flipside = flipside_executor
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

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(self.run_one, qc, dry_run): qc for qc in configs}
            for future in as_completed(futures):
                qc = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = IngestionResult(query_name=qc.query_name, error=exc, provider="flipside")
                results[qc.query_name] = result
                _log_result(result)

        return results

    def run_one(self, qc: QueryConfig, dry_run: bool = False) -> IngestionResult:
        start = time.monotonic()
        result = IngestionResult(query_name=qc.query_name, provider="flipside")

        try:
            sql_template = qc.sql_path.read_text()

            if dry_run:
                logger.info("[%s] DRY RUN — SQL template (%d chars)", qc.query_name, len(sql_template))
                logger.info(sql_template[:500] + ("..." if len(sql_template) > 500 else ""))
                result.success = True
                return result

            rows = self.flipside.execute(qc.query_name, sql_template, qc.params)
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
        names = [n for n in names if n not in FLIPSIDE_UNSUPPORTED]

        effective_global_hours = time_window_hours if time_window_hours is not None else Config.DUNE_QUERY_WINDOW_HOURS
        effective_end_time = end_time or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        result = []
        for name in names:
            per_query = queries_cfg.get(name, {})
            params = {
                **globals_,
                "time_window_hours": effective_global_hours,
                "end_time": effective_end_time,
                **per_query,
            }
            if end_time is not None:
                params["end_time"] = end_time
                params["time_window_hours"] = (
                    time_window_hours if time_window_hours is not None
                    else int(params.get("time_window_hours", effective_global_hours))
                )
            cadence = int(params.get("time_window_hours", effective_global_hours))

            sql_file = self.query_dir / f"{name}.sql"
            if not sql_file.exists():
                logger.warning("[%s] No Flipside SQL file at %s — skipping", name, sql_file)
                continue

            result.append(QueryConfig(
                query_name=name,
                sql_path=sql_file,
                params=params,
                cadence_hours=cadence,
                signal_category=QUERY_TO_SIGNAL[name],
                target_index=QUERY_TO_INDEX[name],
            ))
        return result

    def _add_metadata_envelope(
        self,
        rows: list[dict],
        qc: QueryConfig,
        ingested_at: datetime,
    ) -> list[dict]:
        end_dt = self._resolve_end_dt(qc, ingested_at)
        tw = qc.params.get("time_window_hours")
        window_start = (
            (end_dt - timedelta(hours=int(tw))).isoformat() if tw is not None else None
        )
        _TOKEN_ADDRESS_QUERIES = {"wallet_concentration", "new_holder_growth"}
        token_address = qc.params.get("token_address")
        enriched = []
        for row in rows:
            doc = dict(row)
            doc["ingested_at"]       = ingested_at.isoformat()
            doc["query_name"]        = qc.query_name
            doc["signal_category"]   = qc.signal_category
            doc["time_window_hours"] = int(tw) if tw is not None else None
            doc["window_start"]      = window_start
            doc["params_snapshot"]   = dict(qc.params)
            doc["provider"]          = "flipside"
            if (
                token_address
                and "token_address" not in doc
                and qc.query_name in _TOKEN_ADDRESS_QUERIES
            ):
                doc["token_address"] = token_address
            enriched.append(doc)
        return enriched

    @staticmethod
    def _resolve_end_dt(qc: QueryConfig, ingested_at: datetime) -> datetime:
        raw = qc.params.get("end_time")
        if raw:
            try:
                dt = datetime.fromisoformat(raw)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return ingested_at

    def _make_doc_id(self, qc: QueryConfig, doc: dict, ingested_at: datetime) -> str:
        name = qc.query_name
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
            parts = [str(doc.get("symbol", "")), ws]
        elif name == "token_inflow_outflow":
            parts = [str(doc.get("symbol", "")), ws]
        elif name == "bridge_activity":
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
            parts = [str(doc.get("symbol", "")), str(doc.get("deployment_type", "")), ws]
        else:
            parts = [name, ws]

        return hashlib.sha256("||".join(parts).encode()).hexdigest()[:24]

    def _bulk_index(self, docs: list[dict], index: str) -> tuple[int, list[dict]]:
        actions = [
            {"_index": index, "_id": doc.pop("_id"), "_source": doc}
            for doc in docs
        ]
        result = es_helpers.bulk(self.es, actions, raise_on_error=False)
        if isinstance(result, tuple):
            ok, errors = result
        else:
            ok, errors = result, []
        if not isinstance(errors, (list, tuple)):
            errors = []
        else:
            errors = list(errors)
        if errors:
            for err in errors:
                logger.error("Bulk index error in %s: %s", index, err)
        return ok, errors


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

def build_flipside_pipeline() -> FlipsideIngestionPipeline:
    if not Config.FLIPSIDE_API_KEY:
        raise ValueError("FLIPSIDE_API_KEY is not set — export it or add it to .env")

    es_manager = ElasticsearchManager(
        Config.ES_URL,
        Config.ES_USERNAME,
        Config.ES_PASSWORD,
        Config.ES_API_KEY_ID,
    )
    es_client = es_manager.get_client()

    index_manager = DuneIndexManager(es_client)
    index_manager.ensure_all_indices()

    query_dir = Path(__file__).parent / "flipside_query"
    executor = FlipsideExecutor(
        api_key=Config.FLIPSIDE_API_KEY,
        query_dir=query_dir,
    )

    return FlipsideIngestionPipeline(
        es_client=es_client,
        flipside_executor=executor,
        query_dir=query_dir,
        config_path=query_dir / "config.yaml",
    )
