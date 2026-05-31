"""
schedule_runner.py: long-running loop that drives DuneIngestionPipeline
on per-cadence schedules (6h and 24h groups).

Usage:
  python schedule_runner.py
  python schedule_runner.py --once        # run all groups once and exit
"""

import argparse
import logging
import time
from datetime import datetime, timezone

from ingestion.dune_pipeline import CADENCE_GROUPS, build_pipeline
from ingestion.tempo_executor import TempoPaymentError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

PAYMENT_BACKOFF_SECONDS = 3600   # 1 hour before retrying after payment failure
CHECK_INTERVAL_SECONDS  = 300    # check cadence timers every 5 minutes


def run_scheduler(once: bool = False) -> None:
    pipeline = build_pipeline()

    # Initialise last_run to epoch so every group fires immediately on start
    last_run: dict[int, datetime] = {c: datetime.min.replace(tzinfo=timezone.utc)
                                     for c in CADENCE_GROUPS}
    payment_backoff_until: datetime | None = None

    logger.info("Scheduler started. Groups: %s", dict(CADENCE_GROUPS))

    while True:
        now = datetime.now(timezone.utc)

        if payment_backoff_until and now < payment_backoff_until:
            remaining = int((payment_backoff_until - now).total_seconds())
            logger.info("Payment backoff active — %ds remaining", remaining)
            if not once:
                time.sleep(min(CHECK_INTERVAL_SECONDS, remaining))
                continue

        payment_failed_this_round = False

        for cadence_hours, queries in CADENCE_GROUPS.items():
            elapsed_h = (now - last_run[cadence_hours]).total_seconds() / 3600
            if elapsed_h < cadence_hours:
                continue

            logger.info("Running %dh cadence group: %s", cadence_hours, queries)
            results = pipeline.run_all(query_names=queries)

            # Check for payment failure — no point running more groups
            for r in results.values():
                if isinstance(r.error, TempoPaymentError):
                    payment_failed_this_round = True
                    break

            last_run[cadence_hours] = now

            if payment_failed_this_round:
                payment_backoff_until = now.__class__(
                    now.year, now.month, now.day, now.hour, now.minute, now.second,
                    tzinfo=now.tzinfo
                )
                from datetime import timedelta
                payment_backoff_until = now + timedelta(seconds=PAYMENT_BACKOFF_SECONDS)
                logger.critical(
                    "Payment error — all groups paused until %s. "
                    "Fund wallet at https://wallet.tempo.xyz",
                    payment_backoff_until.isoformat(),
                )
                break  # skip remaining cadence groups this tick

        # Purge docs older than 7 days (runs after every tick that had work)
        try:
            pipeline.purge_old_documents(days=7)
        except Exception as exc:
            logger.warning("Purge failed: %s", exc)

        if once:
            logger.info("--once flag set, exiting.")
            break

        logger.debug("Sleeping %ds until next check.", CHECK_INTERVAL_SECONDS)
        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Dune ingestion scheduler")
    p.add_argument("--once", action="store_true", help="Run all due groups once then exit")
    args = p.parse_args()
    run_scheduler(once=args.once)
