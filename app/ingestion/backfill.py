"""
Historical backfill: runs Dune queries in weekly chunks and indexes results into
Elasticsearch.  wallet_concentration is skipped (current-state snapshot only).

Usage examples:
  python backfill.py --start 2026-03-01 --end 2026-06-05
  python backfill.py --start 2026-03-01 --end 2026-06-05 --chunk-days 7
  python backfill.py --start 2026-03-01 --end 2026-06-05 --queries whale_transaction_filter bridge_activity
  python backfill.py --start 2026-03-01 --end 2026-06-05 --dry-run
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from elasticsearch import Elasticsearch

from config.config import Config
from app.ingestion.dune_api_executor import DuneApiExecutor
from app.ingestion.dune_pipeline import DuneIngestionPipeline, QUERY_TO_INDEX

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# wallet_concentration is a current-state snapshot with no time window — skip in backfill
_SKIP_QUERIES = {"wallet_concentration"}

# 7-day chunks keep each Dune query well under the free-tier timeout
_DEFAULT_CHUNK_DAYS = 7
_DEFAULT_DELAY_SECONDS = 30   # pause between chunks to avoid Dune rate limits
_CHECKPOINT_FILENAME = "backfill_checkpoint.json"


def _checkpoint_key(end_time_str: str, chunk_hours: int) -> str:
    return f"{end_time_str}|{chunk_hours}h"


def _load_checkpoint(query_dir: Path) -> set[str]:
    path = query_dir / _CHECKPOINT_FILENAME
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text())
        return set(data.get("completed", []))
    except Exception:
        return set()


def _save_checkpoint(query_dir: Path, completed: set[str]) -> None:
    path = query_dir / _CHECKPOINT_FILENAME
    path.write_text(json.dumps({"completed": sorted(completed)}, indent=2))


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backfill historical Dune data into Elasticsearch")
    p.add_argument("--start", required=True, help="Start date inclusive, YYYY-MM-DD (UTC)")
    p.add_argument("--end",   required=True, help="End date inclusive, YYYY-MM-DD (UTC)")
    p.add_argument("--chunk-days", type=int, default=_DEFAULT_CHUNK_DAYS,
                   help=f"Days per Dune query window (default {_DEFAULT_CHUNK_DAYS})")
    p.add_argument("--queries", nargs="*",
                   help="Subset of query names to run (default: all except wallet_concentration)")
    p.add_argument("--delay-seconds", type=float, default=_DEFAULT_DELAY_SECONDS,
                   help=f"Seconds to wait between chunks (default {_DEFAULT_DELAY_SECONDS})")
    p.add_argument("--dry-run", action="store_true",
                   help="Print plan without executing any Dune queries or ES writes")
    p.add_argument("--resume", action="store_true",
                   help="Skip chunks already recorded in backfill_checkpoint.json (safe to re-run)")
    p.add_argument("--reset-checkpoint", action="store_true",
                   help="Delete backfill_checkpoint.json and start fresh")
    return p.parse_args()


def _build_chunks(start: datetime, end: datetime, chunk_days: int) -> list[tuple[datetime, datetime]]:
    """
    Return (chunk_start, chunk_end) pairs advancing by chunk_days.
    chunk_end is the exclusive upper bound passed as end_time to SQL.
    The last chunk may be shorter than chunk_days.
    """
    chunks = []
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=chunk_days), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end
    return chunks


def main() -> None:
    args = _parse_args()

    start_dt = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt   = datetime.strptime(args.end,   "%Y-%m-%d").replace(tzinfo=timezone.utc)
    # end date is inclusive — extend to end-of-day
    end_dt   = end_dt.replace(hour=23, minute=59, second=59)

    if start_dt >= end_dt:
        logger.error("--start must be before --end")
        sys.exit(1)

    all_query_names = [q for q in QUERY_TO_INDEX if q not in _SKIP_QUERIES]
    query_names = args.queries if args.queries else all_query_names

    invalid = [q for q in query_names if q not in QUERY_TO_INDEX]
    if invalid:
        logger.error("Unknown query names: %s", invalid)
        sys.exit(1)

    query_names = [q for q in query_names if q not in _SKIP_QUERIES]

    chunks = _build_chunks(start_dt, end_dt, args.chunk_days)
    chunk_hours = args.chunk_days * 24

    logger.info(
        "Backfill plan: %s → %s  |  %d chunk(s) × %d days  |  %d queries  |  dry_run=%s",
        args.start, args.end, len(chunks), args.chunk_days, len(query_names), args.dry_run,
    )
    logger.info("Queries: %s", query_names)

    if args.dry_run:
        for i, (cs, ce) in enumerate(chunks, 1):
            logger.info("[DRY RUN] Chunk %d/%d: end_time=%s  window=%dh",
                        i, len(chunks), ce.strftime("%Y-%m-%d %H:%M:%S"), chunk_hours)
        logger.info("[DRY RUN] Done — no queries executed")
        return

    es_client = Elasticsearch(
        Config.ES_URL,
        api_key=Config.ES_API_KEY_ID,
        request_timeout=60,
    )
    query_dir = Path(__file__).parent / "query"
    executor = DuneApiExecutor(
        api_key=Config.DUNE_API_KEY,
        query_dir=query_dir,
    )
    pipeline = DuneIngestionPipeline(
        es_client=es_client,
        dune_executor=executor,
        query_dir=query_dir,
        config_path=query_dir / "config.yaml",
    )

    total_indexed = 0
    total_failed  = 0

    for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
        end_time_str = chunk_end.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(
            "── Chunk %d/%d  end_time=%s  window=%dh ──",
            i, len(chunks), end_time_str, chunk_hours,
        )

        results = pipeline.run_all(
            query_names=query_names,
            dry_run=False,
            end_time=end_time_str,
            time_window_hours=chunk_hours,
        )

        chunk_indexed = sum(r.docs_indexed for r in results.values())
        chunk_failed  = sum(r.docs_failed  for r in results.values())
        total_indexed += chunk_indexed
        total_failed  += chunk_failed

        errors = [(name, r.error) for name, r in results.items() if r.error]
        if errors:
            for name, err in errors:
                logger.error("  [%s] failed: %s", name, err)

        logger.info("  Chunk result: +%d indexed, %d failed", chunk_indexed, chunk_failed)

        if i < len(chunks):
            logger.info("  Sleeping %gs before next chunk …", args.delay_seconds)
            time.sleep(args.delay_seconds)

    logger.info(
        "Backfill complete: %d chunks, %d docs indexed, %d docs failed",
        len(chunks), total_indexed, total_failed,
    )


if __name__ == "__main__":
    main()
