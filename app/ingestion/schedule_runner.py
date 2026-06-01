"""
schedule_runner.py: long-running loop that drives DuneIngestionPipeline
on per-cadence schedules (6h and 24h groups) and runs automated narrative
detection every NARRATIVE_DETECTION_INTERVAL_HOURS.

Usage:
  python schedule_runner.py
  python schedule_runner.py --once        # run all groups once and exit
"""

import argparse
import logging
import time
from datetime import datetime, timezone

from app.ingestion.dune_pipeline import CADENCE_GROUPS, build_pipeline
from app.ingestion.tempo_executor import TempoPaymentError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

PAYMENT_BACKOFF_SECONDS = 3600   # 1 hour before retrying after payment failure
CHECK_INTERVAL_SECONDS  = 300    # check cadence timers every 5 minutes


def _run_detection(es_manager, engine, tracker, hours: int, user_id: str = "default") -> None:
    """Run a full narrative detection cycle (transform → Gemini → MongoDB)."""
    try:
        from app.synthesize.signal_transformer import run_narrative_generation
        logger.info("[DETECT] Starting detection via signal_transformer (lookback=%dh)", hours)
        result = run_narrative_generation(
            hours=hours,
            user_id=user_id,
            es_manager=es_manager,
            engine=engine,
            tracker=tracker,
        )
        if result:
            logger.info("[DETECT] Saved %d narrative(s) to MongoDB", len(result))
        else:
            logger.info("[DETECT] No narratives returned by Gemini this cycle")
    except Exception as exc:
        logger.error("[DETECT] Detection cycle failed: %s", exc)


def run_scheduler(once: bool = False) -> None:
    from config.config import Config

    detection_interval_hours = Config.NARRATIVE_DETECTION_INTERVAL_HOURS
    query_window_hours        = Config.DUNE_QUERY_WINDOW_HOURS

    pipeline = build_pipeline()

    # Narrative detection services (best-effort — detection is skipped if unavailable)
    try:
        import os
        from app.brain.elasticsearch_manager import ElasticsearchManager
        from app.synthesize.narrative_engine import NarrativeEngine
        from app.synthesize.narrative_tracker import NarrativeTracker

        def _secret(key: str) -> str:
            return os.getenv(key, getattr(Config, key, ""))

        es_manager = ElasticsearchManager(
            _secret("ES_URL"), _secret("ES_USERNAME"),
            _secret("ES_PASSWORD"), _secret("ES_API_KEY_ID"),
        )
        engine  = NarrativeEngine(_secret("GEMINI_KEY") or _secret("GOOGLE_API_KEY"))
        tracker = NarrativeTracker(_secret("MONGO_URI"), _secret("MONGO_DB") or "kairo")
        detection_enabled = True
        logger.info("[DETECT] Narrative detection services ready (interval=%dh)", detection_interval_hours)
    except Exception as exc:
        es_manager = engine = tracker = None
        detection_enabled = False
        logger.warning("[DETECT] Detection services unavailable — detection disabled: %s", exc)

    # Initialise last_run to epoch so every group fires immediately on start
    last_run: dict[int, datetime] = {c: datetime.min.replace(tzinfo=timezone.utc)
                                     for c in CADENCE_GROUPS}
    last_detection: datetime = datetime.min.replace(tzinfo=timezone.utc)
    payment_backoff_until: datetime | None = None

    logger.info("Scheduler started. Ingestion groups: %s | Detection interval: %dh | Query window: %dh",
                dict(CADENCE_GROUPS), detection_interval_hours, query_window_hours)

    while True:
        now = datetime.now(timezone.utc)

        if payment_backoff_until and now < payment_backoff_until:
            remaining = int((payment_backoff_until - now).total_seconds())
            logger.info("Payment backoff active — %ds remaining", remaining)
            if not once:
                time.sleep(min(CHECK_INTERVAL_SECONDS, remaining))
                continue

        payment_failed_this_round = False

        # ── Dune ingestion cadence groups ───────────────────────────────────────
        for cadence_hours, queries in CADENCE_GROUPS.items():
            elapsed_h = (now - last_run[cadence_hours]).total_seconds() / 3600
            if elapsed_h < cadence_hours:
                continue

            logger.info("Running %dh cadence group: %s", cadence_hours, queries)
            results = pipeline.run_all(query_names=queries)

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
                break

        # ── Narrative detection cadence ─────────────────────────────────────────
        if detection_enabled and not payment_failed_this_round:
            elapsed_detect_h = (now - last_detection).total_seconds() / 3600
            if elapsed_detect_h >= detection_interval_hours:
                logger.info("[DETECT] Running scheduled detection (elapsed=%.1fh)", elapsed_detect_h)
                _run_detection(es_manager, engine, tracker, hours=query_window_hours)
                last_detection = now

        # ── Purge old documents ─────────────────────────────────────────────────
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
    p = argparse.ArgumentParser(description="Dune ingestion + narrative detection scheduler")
    p.add_argument("--once", action="store_true", help="Run all due groups once then exit")
    args = p.parse_args()
    run_scheduler(once=args.once)
