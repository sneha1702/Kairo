"""
signal_transformer.py — Fetches Elasticsearch data and builds a unified signal schema
that drives narrative generation.

Three output categories:
  capital_migration  — cross-chain token flows (bridge + whale + token_flows aggregated)
  smart_deployment   — post-bridge smart money positioning into protocols
  stablecoin_flow    — stablecoin mint and net-flow activity

Full pipeline (transform → Gemini → MongoDB):
  python -m app.synthesize.signal_transformer               # default 24 h window
  python -m app.synthesize.signal_transformer --hours 168   # 1-week summary
  python -m app.synthesize.signal_transformer --hours 72 --user-id analyst
  python -m app.synthesize.signal_transformer --dry-run     # transform only, skip Gemini

Bulk / historic backfill (one Gemini call per week, previous week passed as history):
  python -m app.synthesize.signal_transformer --backfill-days 30
  python -m app.synthesize.signal_transformer --backfill-days 90 --sleep-between 30
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure repo root is importable when executed directly
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Symbols treated as stablecoins for the stablecoin_flow category
_STABLECOINS = frozenset({
    "USDC", "USDT", "DAI", "FRAX", "BUSD", "TUSD", "USDP", "GUSD",
    "LUSD", "crvUSD", "USDE", "FDUSD", "PYUSD", "USDD",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _day_bucket(ts: Optional[str]) -> str:
    """Truncate an ISO timestamp string to YYYY-MM-DD."""
    if ts and len(ts) >= 10:
        try:
            return ts[:10]
        except Exception:
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# SignalTransformer
# ---------------------------------------------------------------------------

class SignalTransformer:
    """
    Transforms raw Elasticsearch signal documents into the unified schema.
    Accepts an ElasticsearchManager and delegates all ES calls through it.
    """

    def __init__(self, es_manager: Any) -> None:
        self.es = es_manager

    # ── Public entry point ─────────────────────────────────────────────────

    def build_unified_signals(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Query all 8 dune_* indices for the given lookback window and return
        a flat list of unified signal records (capital_migration, smart_deployment,
        stablecoin_flow).
        """
        logger.info("[TRANSFORM] Fetching ES context — lookback=%dh", hours)
        ctx = self.es.get_dune_signal_context(hours=hours)

        signals: List[Dict[str, Any]] = []
        signals.extend(self._capital_migration(ctx))
        signals.extend(self._smart_deployment(ctx))
        signals.extend(self._stablecoin_flow(ctx))

        logger.info(
            "[TRANSFORM] %d unified records — %d capital_migration, %d smart_deployment, %d stablecoin_flow",
            len(signals),
            sum(1 for s in signals if s["category"] == "capital_migration"),
            sum(1 for s in signals if s["category"] == "smart_deployment"),
            sum(1 for s in signals if s["category"] == "stablecoin_flow"),
        )
        return signals

    # ── capital_migration ──────────────────────────────────────────────────

    def _capital_migration(self, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Bridge_activity + whale_transactions + token_flows →
        one record per (time_bucket, symbol, from_chain, to_chain).
        """
        bridges = ctx.get("bridge_activity", [])
        whales  = ctx.get("whale_transactions", [])
        flows   = ctx.get("token_flows", [])
        wc      = ctx.get("wallet_concentration", [])

        # whale_concentration_pct: max cumulative_pct for top-10 holders per symbol
        conc_map: Dict[str, float] = {}
        for r in wc:
            sym = (r.get("symbol") or r.get("token") or "").upper().strip()
            pct = _num(r.get("cumulative_pct") or r.get("pct_of_supply"))
            if sym and r.get("rank", 999) <= 10 and pct > conc_map.get(sym, 0.0):
                conc_map[sym] = pct

        # key: (time_bucket, symbol, from_chain, to_chain)
        buckets: Dict[tuple, Dict[str, Any]] = {}

        def _touch(tb: str, sym: str, fc: str, tc: str) -> Dict[str, Any]:
            key = (tb, sym, fc, tc)
            if key not in buckets:
                buckets[key] = {
                    "time_bucket": tb,
                    "category":    "capital_migration",
                    "symbol":      sym,
                    "from_chain":  fc,
                    "to_chain":    tc,
                    "signals":     [],
                    "signal_count": 0,
                    "total_usd":   0.0,
                    "net_flow_usd": 0.0,
                    "bridge_usd":  0.0,
                    "whale_usd":   0.0,
                    "whale_concentration_pct": conc_map.get(sym, 0.0),
                }
            return buckets[key]

        def _add_sig(e: Dict, sig: str) -> None:
            if sig not in e["signals"]:
                e["signals"].append(sig)
                e["signal_count"] += 1

        for r in bridges:
            direction = r.get("direction", "")
            sep = "→" if "→" in direction else "->"
            parts  = direction.split(sep) if sep in direction else ["Unknown", "Unknown"]
            from_c = parts[0].strip() if len(parts) > 0 else "Unknown"
            to_c   = parts[1].strip() if len(parts) > 1 else "Unknown"
            sym    = (r.get("symbol") or r.get("token") or "ETH").upper().strip()
            tb     = _day_bucket(r.get("earliest_tx_time") or r.get("ingested_at"))
            e      = _touch(tb, sym, from_c, to_c)
            usd    = _num(r.get("total_usd"))
            e["bridge_usd"] += usd
            e["total_usd"]  += usd
            _add_sig(e, "bridge_activity")

        for r in whales:
            sym = (r.get("symbol") or "").upper().strip()
            if not sym:
                continue
            from_c = r.get("from_chain") or r.get("chain") or "Unknown"
            to_c   = r.get("to_chain")   or r.get("chain") or "Unknown"
            tb     = _day_bucket(r.get("block_time") or r.get("ingested_at"))
            e      = _touch(tb, sym, from_c, to_c)
            usd    = _num(r.get("usd_value"))
            e["whale_usd"] += usd
            e["total_usd"] += usd
            e["whale_concentration_pct"] = max(
                e["whale_concentration_pct"], conc_map.get(sym, 0.0)
            )
            _add_sig(e, "whale_transactions")

        for r in flows:
            sym = (r.get("token") or r.get("symbol") or "").upper().strip()
            if not sym:
                continue
            from_c = r.get("from_chain") or "Unknown"
            to_c   = r.get("to_chain")   or "Unknown"
            tb     = _day_bucket(r.get("window_start") or r.get("ingested_at"))
            e      = _touch(tb, sym, from_c, to_c)
            e["net_flow_usd"] += _num(r.get("net_flow_usd"))
            _add_sig(e, "token_flows")

        result = []
        for e in buckets.values():
            for k in ("total_usd", "net_flow_usd", "bridge_usd", "whale_usd"):
                e[k] = round(e[k])
            e["whale_concentration_pct"] = round(e["whale_concentration_pct"], 1)
            # Remove internal-only whale_usd from output (it's folded into total_usd)
            e.pop("whale_usd", None)
            result.append(e)

        return result

    # ── smart_deployment ───────────────────────────────────────────────────

    def _smart_deployment(self, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Smart_money + wallet_concentration →
        one record per (time_bucket, symbol, to_chain, deployment_type, protocol).
        """
        sm = ctx.get("smart_money", [])
        wc = ctx.get("wallet_concentration", [])

        conc_map: Dict[str, float] = {}
        for r in wc:
            sym = (r.get("symbol") or r.get("token") or "").upper().strip()
            pct = _num(r.get("cumulative_pct") or r.get("pct_of_supply"))
            if sym and r.get("rank", 999) <= 10 and pct > conc_map.get(sym, 0.0):
                conc_map[sym] = pct

        buckets: Dict[tuple, Dict[str, Any]] = {}

        def _touch(tb: str, sym: str, tc: str, dtype: str, proto: str) -> Dict[str, Any]:
            key = (tb, sym, tc, dtype, proto)
            if key not in buckets:
                buckets[key] = {
                    "time_bucket":     tb,
                    "category":        "smart_deployment",
                    "symbol":          sym,
                    "to_chain":        tc,
                    "deployment_type": dtype,
                    "protocol":        proto,
                    "signals":         [],
                    "signal_count":    0,
                    "smart_money_usd": 0.0,
                    "whale_concentration_pct": conc_map.get(sym, 0.0),
                }
            return buckets[key]

        def _add_sig(e: Dict, sig: str) -> None:
            if sig not in e["signals"]:
                e["signals"].append(sig)
                e["signal_count"] += 1

        for r in sm:
            sym   = (r.get("symbol") or "").upper().strip()
            if not sym:
                continue
            to_c  = r.get("to_chain") or r.get("chain") or "Unknown"
            dtype = r.get("deployment_type") or r.get("protocol_type") or "unknown"
            proto = r.get("protocol") or r.get("project") or "Unknown"
            tb    = _day_bucket(r.get("first_buy") or r.get("ingested_at"))
            e     = _touch(tb, sym, to_c, dtype, proto)
            e["smart_money_usd"]          += _num(r.get("total_bought_usd"))
            e["whale_concentration_pct"]   = max(
                e["whale_concentration_pct"], conc_map.get(sym, 0.0)
            )
            acc_sig = r.get("accumulation_signal") or ""
            sig_name = "post_bridge_deployment" if "bridge" in acc_sig.lower() else "smart_money"
            _add_sig(e, sig_name)

        result = []
        for e in buckets.values():
            e["smart_money_usd"]          = round(e["smart_money_usd"])
            e["whale_concentration_pct"]  = round(e["whale_concentration_pct"], 1)
            result.append(e)

        return result

    # ── stablecoin_flow ────────────────────────────────────────────────────

    def _stablecoin_flow(self, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Token_flows filtered to stablecoin symbols →
        one record per (time_bucket, symbol).
        """
        flows = ctx.get("token_flows", [])

        buckets: Dict[tuple, Dict[str, Any]] = {}

        def _touch(tb: str, sym: str) -> Dict[str, Any]:
            key = (tb, sym)
            if key not in buckets:
                buckets[key] = {
                    "time_bucket":  tb,
                    "category":     "stablecoin_flow",
                    "symbol":       sym,
                    "net_flow_usd": 0.0,
                    "mint_usd":     0.0,
                    "signals":      [],
                    "signal_count": 0,
                }
            return buckets[key]

        def _add_sig(e: Dict, sig: str) -> None:
            if sig not in e["signals"]:
                e["signals"].append(sig)
                e["signal_count"] += 1

        for r in flows:
            sym = (r.get("token") or r.get("symbol") or "").upper().strip()
            if sym not in _STABLECOINS:
                continue
            tb  = _day_bucket(r.get("window_start") or r.get("ingested_at"))
            e   = _touch(tb, sym)
            net  = _num(r.get("net_flow_usd"))
            infl = _num(r.get("inflow_usd"))
            e["net_flow_usd"] += net
            e["mint_usd"]     += infl  # inflow to on-chain wallets proxies new supply/mint
            if infl > 0:
                _add_sig(e, "stablecoin_mint")
            elif net != 0:
                raw_sig = r.get("signal") or "stablecoin_flow"
                _add_sig(e, raw_sig)

        result = []
        for e in buckets.values():
            e["net_flow_usd"] = round(e["net_flow_usd"])
            e["mint_usd"]     = round(e["mint_usd"])
            result.append(e)

        return result


# ---------------------------------------------------------------------------
# Acceleration enrichment
# ---------------------------------------------------------------------------

def enrich_with_acceleration(
    signals: List[Dict[str, Any]],
    es_manager: Any,
) -> List[Dict[str, Any]]:
    """
    Add acceleration_7d_vs_30d_pct to each capital_migration record.
    Compares the daily bridge run-rate over the past 7 days vs. 30 days.
    """
    logger.info("[TRANSFORM] Enriching with 7d vs 30d bridge acceleration")
    try:
        trend_7d  = es_manager.get_signal_trend(hours_per_bucket=168, num_buckets=1)
        trend_30d = es_manager.get_signal_trend(hours_per_bucket=720, num_buckets=1)
    except Exception as exc:
        logger.warning("[TRANSFORM] Could not fetch acceleration trends: %s", exc)
        return signals

    bridge_7d  = trend_7d[0]["bridge_usd"]  if trend_7d  else 0.0
    bridge_30d = trend_30d[0]["bridge_usd"] if trend_30d else 0.0

    # Convert to daily rates so windows are comparable
    daily_7d  = bridge_7d  / 7  if bridge_7d  > 0 else 0.0
    daily_30d = bridge_30d / 30 if bridge_30d > 0 else 0.0

    if daily_30d > 0:
        acceleration_pct = round((daily_7d / daily_30d - 1) * 100)
    else:
        acceleration_pct = None

    enriched = []
    for s in signals:
        if s.get("category") == "capital_migration" and acceleration_pct is not None:
            s = {**s, "acceleration_7d_vs_30d_pct": acceleration_pct}
        enriched.append(s)

    return enriched


# ---------------------------------------------------------------------------
# End-to-end narrative generation pipeline
# ---------------------------------------------------------------------------

def run_narrative_generation(
    hours: int = 24,
    user_id: str = "default",
    es_manager: Any = None,
    engine: Any = None,
    tracker: Any = None,
    dry_run: bool = False,
    prior_narratives: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Full pipeline: transform ES signals → Gemini → MongoDB.

    Can be called by schedule_runner (services pre-created) or standalone
    (services are initialised from Config when not supplied).

    Args:
        hours:            ES lookback window in hours (default 24).
        user_id:          MongoDB user partition key.
        es_manager:       Pre-created ElasticsearchManager (or None to auto-create).
        engine:           Pre-created NarrativeEngine (or None to auto-create).
        tracker:          Pre-created NarrativeTracker (or None to auto-create).
        dry_run:          If True, transform and log but skip Gemini + MongoDB write.
        prior_narratives: Narratives from the previous backfill window to inject as
                          history. When supplied, skips the MongoDB history query so
                          the backfill loop doesn't depend on DB write propagation.

    Returns:
        List of enriched narrative dicts that were saved (empty on dry_run or failure).
    """
    from config.config import Config
    from app.brain.elasticsearch_manager import ElasticsearchManager
    from app.synthesize.narrative_engine import NarrativeEngine
    from app.synthesize.narrative_tracker import NarrativeTracker

    def _secret(key: str) -> str:
        return os.getenv(key, getattr(Config, key, ""))

    if es_manager is None:
        logger.info("[NARR] Creating ElasticsearchManager from Config")
        es_manager = ElasticsearchManager(
            _secret("ES_URL"), _secret("ES_USERNAME"),
            _secret("ES_PASSWORD"), _secret("ES_API_KEY_ID"),
        )
    if engine is None:
        logger.info("[NARR] Creating NarrativeEngine from Config")
        engine = NarrativeEngine(_secret("GEMINI_KEY") or _secret("GOOGLE_API_KEY"))
    if tracker is None:
        logger.info("[NARR] Creating NarrativeTracker from Config")
        tracker = NarrativeTracker(_secret("MONGO_URI"), _secret("MONGO_DB") or "kairo")

    # ── Step 1: build unified signal schema ────────────────────────────────
    transformer     = SignalTransformer(es_manager)
    unified_signals = transformer.build_unified_signals(hours=hours)
    unified_signals = enrich_with_acceleration(unified_signals, es_manager)

    if dry_run:
        logger.info("[NARR] dry-run — skipping Gemini and MongoDB")
        _dump_signals(unified_signals)
        return []

    # ── Step 2: fetch full context and trend for the Gemini prompt ─────────
    logger.info("[NARR] Fetching full dune context and signal trend")
    dune_context = es_manager.get_dune_signal_context(hours=hours)
    bucket_h     = max(24, hours // 3)
    signal_trend = es_manager.get_signal_trend(hours_per_bucket=bucket_h, num_buckets=3)

    # ── Step 3: load narrative history ────────────────────────────────────
    # During backfill, prior_narratives is passed directly from the previous
    # window so we don't depend on MongoDB write propagation between windows.
    current_narratives = tracker.get_current_narratives(user_id, min_confidence=0.0)
    if prior_narratives is not None:
        history_summary = prior_narratives
        logger.info("[NARR] Using %d prior-window narratives as history context", len(history_summary))
    else:
        history_summary = tracker.get_narratives_summary(user_id)

    # ── Step 4: call Gemini ────────────────────────────────────────────────
    logger.info("[NARR] Calling Gemini narrative detection (window=%dh)", hours)
    new_narratives = engine.detect_narratives(
        dune_context=dune_context,
        historical_narratives=history_summary,
        signal_trend=signal_trend,
        unified_signals=unified_signals,
    )

    if not new_narratives:
        logger.info("[NARR] No narratives returned by Gemini")
        return []

    # ── Step 5: enrich momentum ────────────────────────────────────────────
    enriched = [
        engine.enrich_narrative(n, previous_narratives=current_narratives)
        for n in new_narratives
    ]

    # ── Step 6: attach unified signals as metadata on each narrative ───────
    signal_meta = {
        "window_hours":  hours,
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "total_records": len(unified_signals),
        "by_category": {
            "capital_migration": sum(
                1 for s in unified_signals if s["category"] == "capital_migration"
            ),
            "smart_deployment":  sum(
                1 for s in unified_signals if s["category"] == "smart_deployment"
            ),
            "stablecoin_flow":   sum(
                1 for s in unified_signals if s["category"] == "stablecoin_flow"
            ),
        },
    }
    for n in enriched:
        n["unified_signals"] = unified_signals
        n["signal_metadata"] = signal_meta

    # ── Step 7: persist to MongoDB ─────────────────────────────────────────
    tracker.save_narratives(enriched, user_id)
    returned_ids = {n.get("narrative_id") for n in enriched}
    tracker.mark_stale_narratives(returned_ids, user_id)

    logger.info(
        "[NARR] Saved %d narrative(s) to MongoDB with %d unified signal records as metadata",
        len(enriched), len(unified_signals),
    )
    return enriched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dump_signals(signals: List[Dict[str, Any]]) -> None:
    def _default(obj: Any) -> str:
        return str(obj)
    print(json.dumps(signals, indent=2, default=_default))


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Transform ES signals and generate narratives via Gemini."
    )
    p.add_argument(
        "--hours",
        type=int,
        default=24,
        help="ES lookback window in hours (default: 24)",
    )
    p.add_argument(
        "--user-id",
        default="default",
        help="MongoDB user partition key (default: 'default')",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Transform and print signals only; skip Gemini and MongoDB write",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    # ── Bulk / historic backfill ────────────────────────────────────────────
    p.add_argument(
        "--backfill-days",
        type=int,
        default=0,
        help=(
            "Generate narratives for the last N days in 24-hour chunks. "
            "Overrides --hours when > 0. Processes oldest window first."
        ),
    )
    p.add_argument(
        "--sleep-between",
        type=int,
        default=15,
        help=(
            "Seconds to sleep between Gemini calls during backfill "
            "(default: 15 — stays well under 10 RPM free-tier limit)."
        ),
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("pymongo.topology").setLevel(logging.WARNING)

    if args.backfill_days > 0:
        # ── Backfill mode: one Gemini call per 7-day (168h) window ───────────
        # Windows are expressed as "hours of lookback from now", oldest first.
        # e.g. 21 days → [504, 336, 168]  (3 weekly summaries)
        chunk_hours = 168  # 1 week per Gemini call
        total_hours = args.backfill_days * 24
        windows = list(range(total_hours, 0, -chunk_hours))
        if not windows:
            windows = [total_hours]  # less than a week: one call
        logger.info(
            "Backfill mode — %d day(s), %d weekly window(s), %ds sleep between calls",
            args.backfill_days, len(windows), args.sleep_between,
        )

        from config.config import Config
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

        total_saved     = 0
        prior_narratives: Optional[List[Dict[str, Any]]] = None  # chained between windows

        for i, window_hours in enumerate(windows, 1):
            logger.info(
                "[BACKFILL] Window %d/%d — lookback %dh (~%d days)",
                i, len(windows), window_hours, window_hours // 24,
            )
            try:
                result = run_narrative_generation(
                    hours=window_hours,
                    user_id=args.user_id,
                    es_manager=es_manager,
                    engine=engine,
                    tracker=tracker,
                    dry_run=args.dry_run,
                    prior_narratives=prior_narratives,
                )
                total_saved += len(result)
                # Pass this window's output as history to the next window so
                # Gemini won't recreate the same narratives.
                prior_narratives = result if result else prior_narratives
                logger.info(
                    "[BACKFILL] Window %d/%d done — %d narrative(s) saved",
                    i, len(windows), len(result),
                )
            except Exception as exc:
                logger.error("[BACKFILL] Window %d/%d failed: %s", i, len(windows), exc)

            if i < len(windows):
                logger.info("[BACKFILL] Sleeping %ds before next call …", args.sleep_between)
                time.sleep(args.sleep_between)

        logger.info("Backfill complete — %d total narrative(s) saved.", total_saved)

    else:
        # ── Single-window mode (original behaviour) ──────────────────────────
        logger.info(
            "Starting signal transformer — hours=%d, user_id=%s, dry_run=%s",
            args.hours, args.user_id, args.dry_run,
        )

        result = run_narrative_generation(
            hours=args.hours,
            user_id=args.user_id,
            dry_run=args.dry_run,
        )

        if result:
            logger.info("Done — %d narrative(s) generated and saved.", len(result))
        elif not args.dry_run:
            logger.info("Done — no narratives generated this run.")
