"""
Provider-agnostic ingestion runner.

Selects the pipeline implementation (Dune, DefiLlama, …) at runtime based on
the --provider flag or the INGESTION_PROVIDER env var, then runs it with the
same arguments as the individual pipeline CLIs.

Usage:
  python pipeline_runner.py                              # uses INGESTION_PROVIDER env var (default: dune)
  python pipeline_runner.py --provider defillama
  python pipeline_runner.py --provider dune --queries whale_transaction_filter
  python pipeline_runner.py --provider defillama --cadence 6
  python pipeline_runner.py --provider defillama --dry-run
"""

import argparse
import logging
import sys
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.ingestion.base_pipeline import BaseIngestionPipeline, QUERY_TO_INDEX, CADENCE_GROUPS
from config.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ("dune", "flipside")


def build_pipeline(provider: str) -> BaseIngestionPipeline:
    """Instantiate and return the pipeline for the requested provider."""
    provider = provider.lower()
    if provider == "dune":
        from app.ingestion.dune_pipeline import build_pipeline as _build
        return _build()
    if provider == "flipside":
        from app.ingestion.flipside_pipeline import build_flipside_pipeline as _build
        return _build()
    raise ValueError(
        f"Unknown provider '{provider}'. Supported: {', '.join(SUPPORTED_PROVIDERS)}"
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Provider-agnostic ingestion runner")
    p.add_argument(
        "--provider",
        default=os.getenv("INGESTION_PROVIDER", "dune"),
        choices=list(SUPPORTED_PROVIDERS),
        help="Ingestion provider (default: $INGESTION_PROVIDER or 'dune')",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--queries", nargs="+", choices=list(QUERY_TO_INDEX.keys()),
        metavar="QUERY", help="Run specific queries by name",
    )
    group.add_argument(
        "--cadence", type=int, choices=[6, 24],
        help="Run only queries for this cadence group (6 or 24 hours)",
    )
    p.add_argument("--dry-run", action="store_true", help="Resolve SQL but skip execution")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.cadence:
        query_names = CADENCE_GROUPS[args.cadence]
    else:
        query_names = args.queries  # None = all

    logger.info("Provider: %s", args.provider)
    pipeline = build_pipeline(args.provider)
    results = pipeline.run_all(query_names=query_names, dry_run=args.dry_run)

    failed = [r for r in results.values() if not r.success]
    if failed:
        logger.error("%d queries failed: %s", len(failed), [r.query_name for r in failed])
        sys.exit(1)
    logger.info("All queries completed successfully.")
