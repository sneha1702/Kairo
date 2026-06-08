"""
DefiLlamaIngestionPipeline: implements BaseIngestionPipeline using DefiLlama's
free public REST API.

Supported signals (6/12):
  protocol_inflow_leaderboard → /protocol/{slug} — HISTORICAL: full TVL time series
  bridge_activity             → /protocols (bridge category) — CURRENT STATE ONLY
  stablecoin_liquidity_flow   → /stablecoins — CURRENT STATE ONLY
  ecosystem_sector_rotation   → /protocols grouped by category — CURRENT STATE ONLY

Backfill-skipped signals — DefiLlama has no historical free-tier endpoint:
  volume_spike_detection      → /overview/dexs only has current 24h window
  dex_trading_concentration   → /overview/dexs only has current 24h window

Unsupported signals (6/12) — require per-wallet/per-tx on-chain data:
  whale_transaction_filter, smart_money_accumulation, token_inflow_outflow,
  wallet_concentration, new_holder_growth, post_bridge_deployment
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.ingestion.base_pipeline import (
    BaseIngestionPipeline,
    CADENCE_GROUPS,
    QUERY_TO_INDEX,
    QUERY_TO_SIGNAL,
    IngestionResult,
    QueryConfig,
)
from app.ingestion.defillama_client import DefiLlamaClient, DefiLlamaApiError
from app.ingestion import signal_transformer

logger = logging.getLogger(__name__)

# Signals that require per-wallet / per-tx on-chain data — not available from
# DefiLlama's pre-aggregated endpoints.
_UNSUPPORTED = frozenset({
    "whale_transaction_filter",
    "smart_money_accumulation",
    "token_inflow_outflow",
    "wallet_concentration",
    "new_holder_growth",
    "post_bridge_deployment",
})

# Protocol slugs used by DefiLlama
_PROTOCOL_SLUGS = {
    "aave-v3":    "Aave V3",
    "lido":       "Lido",
    "eigenlayer": "EigenLayer",
}

# Signals where DefiLlama only exposes the current snapshot — no historical
# parameter exists in the free API. Skip these when end_time is in the past
# (backfill mode) to avoid storing misleading current-state data under a
# historical time_bucket label.
#
# NOT included here (historical data IS available):
#   bridge_activity             — fixed to use per-protocol /protocol/{slug} TVL series
#   protocol_inflow_leaderboard — uses /protocol/{slug} TVL series via _tvl_at()
_NO_HISTORICAL_DATA = frozenset({
    "volume_spike_detection",
    "dex_trading_concentration",
    # /stablecoins returns current circulating supply with no date parameter
    "stablecoin_liquidity_flow",
    # /protocols returns current TVL; computing historical sector breakdown
    # would require hundreds of individual /protocol/{slug} calls
    "ecosystem_sector_rotation",
})

# How many hours in the past end_time must be to consider this a backfill call.
_BACKFILL_THRESHOLD_HOURS = 48


def _utcnow_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_end_dt(end_time: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM:SS' (or ISO) to UTC datetime."""
    dt = datetime.fromisoformat(end_time.replace(" ", "T"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _is_backfill(end_time: str) -> bool:
    """True when end_time is more than _BACKFILL_THRESHOLD_HOURS hours in the past."""
    try:
        end_dt = _parse_end_dt(end_time)
        return (datetime.now(timezone.utc) - end_dt) > timedelta(hours=_BACKFILL_THRESHOLD_HOURS)
    except (ValueError, TypeError):
        return False


def _log_fetch_summary(query_name: str, rows: list[dict]) -> None:
    """Log a compact data summary so duplicate-data issues are visible in logs."""
    if not rows:
        return
    tb = rows[0].get("time_bucket", "?")
    if query_name == "bridge_activity":
        sample = "  |  ".join(
            f"{r.get('bridge_name','?')}  TVL=${r.get('tvl_usd',0)/1e9:.2f}B  Δ${r.get('net_flow_usd',0)/1e6:.1f}M"
            for r in rows[:3]
        )
    elif query_name == "stablecoin_liquidity_flow":
        sample = "  |  ".join(
            f"{r.get('symbol','?')}  ${r.get('circulating_usd',0)/1e9:.2f}B  Δ${r.get('delta_usd',0)/1e6:.1f}M"
            for r in rows[:3]
        )
    elif query_name == "ecosystem_sector_rotation":
        sample = "  |  ".join(
            f"{r.get('category','?')}  ${r.get('tvl_usd',0)/1e9:.2f}B  {r.get('tvl_change_pct',0):+.2f}%"
            for r in rows[:3]
        )
    elif query_name == "protocol_inflow_leaderboard":
        sample = "  |  ".join(
            f"{r.get('symbol','?')}  TVL=${r.get('tvl_usd',0)/1e9:.2f}B  Δ${r.get('net_flow_usd',0)/1e6:.1f}M"
            for r in rows[:3]
        )
    else:
        sample = f"{len(rows)} rows"
    logger.info("[%s] time_bucket=%s  data: %s", query_name, tb, sample)


def _tvl_at(series: list[dict], end_ts: int, field: str = "totalLiquidityUSD") -> float:
    """
    Return the value of *field* for the latest entry in *series* whose date <= end_ts.
    *series* must be sorted chronologically (ascending date), as DefiLlama returns it.
    """
    val = 0.0
    for entry in series:
        if entry.get("date", 0) <= end_ts:
            val = entry.get(field) or 0.0
        else:
            break
    return val


class DefiLlamaIngestionPipeline(BaseIngestionPipeline):
    provider_name = "defillama"

    def __init__(self, es_client: Any, client: DefiLlamaClient | None = None):
        self._es = es_client
        self._client = client or DefiLlamaClient()

    # ── BaseIngestionPipeline interface ──────────────────────────────────────────

    def run_all(
        self,
        query_names: list[str] | None = None,
        dry_run: bool = False,
        end_time: str | None = None,
        time_window_hours: int | None = None,
    ) -> dict[str, IngestionResult]:
        # Always clear the HTTP cache so each run_all() (i.e. each backfill chunk)
        # fetches fresh data instead of reusing the previous chunk's cached responses.
        self._client.clear_cache()

        resolved_end = end_time or _utcnow_str()
        backfill_mode = _is_backfill(resolved_end)
        if backfill_mode:
            logger.info(
                "Backfill mode detected (end_time=%s). Signals without historical "
                "DefiLlama data will be skipped: %s",
                resolved_end, sorted(_NO_HISTORICAL_DATA),
            )

        names = query_names if query_names else list(QUERY_TO_INDEX.keys())
        results: dict[str, IngestionResult] = {}
        for name in names:
            qc = QueryConfig(
                query_name=name,
                sql_path=Path("."),
                params={
                    "end_time": resolved_end,
                    "time_window_hours": time_window_hours or 168,
                },
                cadence_hours=24,
                signal_category=QUERY_TO_SIGNAL.get(name, ""),
                target_index=QUERY_TO_INDEX.get(name, name),
            )
            results[name] = self.run_one(qc, dry_run=dry_run, backfill=backfill_mode)
        return results

    def run_one(self, qc: QueryConfig, dry_run: bool = False, backfill: bool = False) -> IngestionResult:
        t0 = time.time()
        result = IngestionResult(
            query_name=qc.query_name,
            provider=self.provider_name,
        )

        if qc.query_name in _UNSUPPORTED:
            logger.info("[%s] Skipped — not supported by DefiLlama", qc.query_name)
            result.success = True
            result.duration_seconds = time.time() - t0
            return result

        if backfill and qc.query_name in _NO_HISTORICAL_DATA:
            logger.info(
                "[%s] Skipped — DefiLlama /overview/dexs only exposes the current "
                "24h window; storing it under a historical time_bucket would be misleading",
                qc.query_name,
            )
            result.success = True
            result.duration_seconds = time.time() - t0
            return result

        if dry_run:
            logger.info("[%s] [DRY RUN] Would fetch from DefiLlama", qc.query_name)
            result.success = True
            result.duration_seconds = time.time() - t0
            return result

        try:
            raw_rows = self._dispatch(qc)
            result.rows_fetched = len(raw_rows)
            logger.info("[%s] Fetched %d rows", qc.query_name, len(raw_rows))

            if raw_rows:
                docs = signal_transformer.normalize(
                    query_name=qc.query_name,
                    provider=self.provider_name,
                    raw_rows=raw_rows,
                    qc=qc,
                )
                indexed, failed = self._bulk_index(docs, qc.target_index)
                result.docs_indexed = indexed
                result.docs_failed  = failed

            result.success = True
        except DefiLlamaApiError as exc:
            logger.error("[%s] DefiLlama error: %s", qc.query_name, exc)
            result.error = exc
        except Exception as exc:
            logger.exception("[%s] Unexpected error: %s", qc.query_name, exc)
            result.error = exc

        result.duration_seconds = time.time() - t0
        return result

    # ── Dispatcher ───────────────────────────────────────────────────────────────

    def _dispatch(self, qc: QueryConfig) -> list[dict]:
        name = qc.query_name
        params = qc.params
        dispatch = {
            "volume_spike_detection":      self._fetch_volume_spike,
            "dex_trading_concentration":   self._fetch_dex_concentration,
            "bridge_activity":             self._fetch_bridge_activity,
            "stablecoin_liquidity_flow":   self._fetch_stablecoin_flow,
            "ecosystem_sector_rotation":   self._fetch_sector_rotation,
            "protocol_inflow_leaderboard": self._fetch_protocol_inflow,
        }
        return dispatch[name](params)

    # ── Signal fetch methods ─────────────────────────────────────────────────────

    def _fetch_volume_spike(self, params: dict) -> list[dict]:
        # Fetch all DEXes (no chain filter — chain param changes response shape)
        data = self._client.dex_overview()
        end_time = params.get("end_time", _utcnow_str())
        # Keep only protocols that have Ethereum in their chain list
        all_protocols = data.get("protocols", [])
        protocols = [
            p for p in all_protocols
            if "Ethereum" in (p.get("chains") or [])
        ]
        rows = []
        for p in protocols:
            vol_24h   = p.get("totalVolume24h") or 0
            vol_7d    = p.get("totalVolume7d")  or 0
            change_1d = p.get("change_1d") or 0
            change_7d = p.get("change_7d") or 0
            if vol_24h <= 0:
                continue

            signals = []
            if change_1d >= 100:
                signals.append("EXTREME_VOLUME_SPIKE")
            elif change_1d >= 50:
                signals.append("HIGH_VOLUME_SPIKE")
            elif change_1d >= 20:
                signals.append("MODERATE_VOLUME_SPIKE")
            if change_1d >= 50 and change_7d >= 50:
                signals.append("SUSTAINED_VOLUME_GROWTH")

            rows.append({
                "symbol":          p.get("name", ""),
                "volume_24h_usd":  round(vol_24h, 2),
                "volume_7d_usd":   round(vol_7d, 2),
                "change_1d_pct":   round(change_1d, 2),
                "change_7d_pct":   round(change_7d, 2),
                "time_bucket":     end_time,
                "category":        "volume_spike",
                "signals":         signals,
                "signal_count":    len(signals),
            })
        return sorted(rows, key=lambda r: r["volume_24h_usd"], reverse=True)[:20]

    def _fetch_dex_concentration(self, params: dict) -> list[dict]:
        data = self._client.dex_overview()
        end_time = params.get("end_time", _utcnow_str())
        all_protocols = data.get("protocols", [])
        protocols = [
            p for p in all_protocols
            if "Ethereum" in (p.get("chains") or []) and (p.get("totalVolume24h") or 0) > 0
        ]

        total_vol = sum(p.get("totalVolume24h", 0) or 0 for p in protocols)
        if total_vol <= 0:
            return []

        rows = []
        cumulative = 0.0
        for rank, p in enumerate(
            sorted(protocols, key=lambda x: x.get("totalVolume24h", 0), reverse=True)[:20],
            start=1,
        ):
            vol = p.get("totalVolume24h", 0) or 0
            pct = round(vol / total_vol * 100, 4)
            cumulative = round(cumulative + pct, 2)

            signals = []
            if rank == 1 and pct >= 50:
                signals.append("DOMINANT_DEX")
            if pct >= 30:
                signals.append("HIGH_MARKET_SHARE")
            if cumulative >= 80 and rank <= 3:
                signals.append("CONCENTRATED_MARKET")

            rows.append({
                "symbol":         p.get("name", ""),
                "rank":           rank,
                "volume_24h_usd": round(vol, 2),
                "market_share_pct": pct,
                "cumulative_pct": cumulative,
                "time_bucket":    end_time,
                "category":       "dex_liquidity",
                "signals":        signals,
                "signal_count":   len(signals),
            })
        return rows

    def _fetch_bridge_activity(self, params: dict) -> list[dict]:
        """
        Uses /protocols (free) filtered to Bridge category on Ethereum.
        TVL change_1d acts as a proxy for net inflow/outflow.
        """
        end_time  = params.get("end_time", _utcnow_str())
        protocols = self._client.protocols()

        rows = []
        for p in protocols:
            if (p.get("category") or "").lower() != "bridge":
                continue
            if "Ethereum" not in (p.get("chains") or []):
                continue

            tvl       = p.get("tvl") or 0
            change_1d = p.get("change_1d") or 0.0
            prev_tvl  = tvl / (1 + change_1d / 100) if change_1d != -100 else tvl
            net_flow  = tvl - prev_tvl

            signals = []
            if net_flow >= 50_000_000:
                signals.append("HIGH_BRIDGE_INFLOW")
            if net_flow <= -10_000_000:
                signals.append("NET_BRIDGE_OUTFLOW")
            if change_1d >= 20:
                signals.append("ACCELERATING_BRIDGE_VOLUME")
            if tvl >= 1_000_000_000:
                signals.append("LARGE_BRIDGE_TVL")

            rows.append({
                "bridge_name":       p.get("name", ""),
                "tvl_usd":           round(tvl, 2),
                "prev_tvl_usd":      round(prev_tvl, 2),
                "net_flow_usd":      round(net_flow, 2),
                "change_1d_pct":     round(change_1d, 2),
                "chains":            p.get("chains", []),
                "time_bucket":       end_time,
                "category":          "bridge",
                "signals":           signals,
                "signal_count":      len(signals),
            })

        return sorted(rows, key=lambda r: r["tvl_usd"], reverse=True)[:15]

    def _fetch_stablecoin_flow(self, params: dict) -> list[dict]:
        end_time = params.get("end_time", _utcnow_str())
        data  = self._client.stablecoins()
        coins = data.get("peggedAssets", [])

        rows = []
        for coin in coins:
            current_usd  = (coin.get("circulating", {}) or {}).get("peggedUSD", 0) or 0
            prev_day_usd = (coin.get("circulatingPrevDay", {}) or {}).get("peggedUSD", 0) or 0

            if current_usd <= 0:
                continue

            delta_usd = current_usd - prev_day_usd
            change_pct = round(delta_usd / prev_day_usd * 100, 2) if prev_day_usd else 0

            signals = []
            if delta_usd >= 100_000_000:
                signals.append("LARGE_STABLECOIN_MINT")
            if delta_usd <= -100_000_000:
                signals.append("LARGE_STABLECOIN_BURN")
            if change_pct >= 5:
                signals.append("RAPID_SUPPLY_EXPANSION")
            if change_pct <= -5:
                signals.append("RAPID_SUPPLY_CONTRACTION")

            rows.append({
                "symbol":          coin.get("symbol", ""),
                "name":            coin.get("name", ""),
                "circulating_usd": round(current_usd, 2),
                "prev_day_usd":    round(prev_day_usd, 2),
                "delta_usd":       round(delta_usd, 2),
                "change_pct":      change_pct,
                "peg_type":        coin.get("pegType", ""),
                "time_bucket":     end_time,
                "category":        "stablecoin_flow",
                "signals":         signals,
                "signal_count":    len(signals),
            })

        return sorted(rows, key=lambda r: r["circulating_usd"], reverse=True)[:20]

    def _fetch_sector_rotation(self, params: dict) -> list[dict]:
        end_time = params.get("end_time", _utcnow_str())
        protocols = self._client.protocols()

        # Group by category, sum TVL + TVL change
        from collections import defaultdict
        by_category: dict[str, dict] = defaultdict(lambda: {
            "tvl": 0.0, "tvl_prev": 0.0, "protocol_count": 0,
        })

        for p in protocols:
            cat = p.get("category") or "Other"
            chains = p.get("chains", [])
            if "Ethereum" not in chains:
                continue

            tvl = p.get("tvl") or 0
            change_1d_pct = p.get("change_1d") or 0
            prev_tvl = tvl / (1 + change_1d_pct / 100) if change_1d_pct != -100 else tvl

            by_category[cat]["tvl"]            += tvl
            by_category[cat]["tvl_prev"]       += prev_tvl
            by_category[cat]["protocol_count"] += 1

        rows = []
        for cat, agg in by_category.items():
            tvl      = agg["tvl"]
            tvl_prev = agg["tvl_prev"]
            if tvl <= 0:
                continue

            delta_pct = round((tvl - tvl_prev) / tvl_prev * 100, 2) if tvl_prev else 0

            signals = []
            if delta_pct >= 20:
                signals.append("STRONG_SECTOR_INFLOW")
            elif delta_pct >= 5:
                signals.append("MODERATE_SECTOR_INFLOW")
            if delta_pct <= -20:
                signals.append("STRONG_SECTOR_OUTFLOW")
            elif delta_pct <= -5:
                signals.append("MODERATE_SECTOR_OUTFLOW")

            rows.append({
                "category":       cat,
                "tvl_usd":        round(tvl, 2),
                "tvl_prev_usd":   round(tvl_prev, 2),
                "tvl_change_pct": delta_pct,
                "protocol_count": agg["protocol_count"],
                "time_bucket":    end_time,
                "signal_category": "sector_rotation",
                "signals":        signals,
                "signal_count":   len(signals),
            })

        return sorted(rows, key=lambda r: r["tvl_usd"], reverse=True)[:15]

    def _fetch_protocol_inflow(self, params: dict) -> list[dict]:
        end_time = params.get("end_time", _utcnow_str())
        rows = []

        for slug, display_name in _PROTOCOL_SLUGS.items():
            try:
                data = self._client.protocol(slug)
            except DefiLlamaApiError as exc:
                logger.warning("[protocol_inflow_leaderboard] %s: %s", slug, exc)
                continue

            # tvl field is a list of {date, totalLiquidityUSD}
            tvl_series = data.get("tvl", [])
            if not tvl_series:
                continue

            current_tvl = tvl_series[-1].get("totalLiquidityUSD", 0) or 0
            prev_tvl    = tvl_series[-2].get("totalLiquidityUSD", 0) if len(tvl_series) >= 2 else current_tvl
            delta_usd   = current_tvl - prev_tvl
            multiplier  = round(current_tvl / prev_tvl, 2) if prev_tvl else None

            signals = []
            if delta_usd >= 100_000_000:
                signals.append("HIGH_PROTOCOL_INFLOW")
            if delta_usd <= -100_000_000:
                signals.append("HIGH_PROTOCOL_OUTFLOW")
            if multiplier and multiplier >= 2.0:
                signals.append("ACCELERATING_INFLOW")
            if current_tvl >= 1_000_000_000:
                signals.append("BILLION_DOLLAR_PROTOCOL")

            rows.append({
                "symbol":            display_name,
                "slug":              slug,
                "tvl_usd":           round(current_tvl, 2),
                "prev_tvl_usd":      round(prev_tvl, 2),
                "net_flow_usd":      round(delta_usd, 2),
                "volume_multiplier": multiplier,
                "time_bucket":       end_time,
                "category":          "protocol_inflow",
                "signals":           signals,
                "signal_count":      len(signals),
            })

        return sorted(rows, key=lambda r: r["tvl_usd"], reverse=True)

    # ── Elasticsearch bulk index ─────────────────────────────────────────────────

    def _bulk_index(self, docs: list[dict], index: str) -> tuple[int, int]:
        from elasticsearch.helpers import bulk, BulkIndexError

        actions = []
        for doc in docs:
            doc = dict(doc)
            doc_id = doc.pop("_id", None)
            action: dict = {"_index": index, "_source": doc}
            if doc_id:
                action["_id"] = doc_id
            actions.append(action)

        try:
            success, errors = bulk(self._es, actions, raise_on_error=False)
            failed = len(errors) if errors else 0
            if errors:
                for err in errors[:3]:
                    logger.warning("Index error: %s", err)
            return success, failed
        except BulkIndexError as exc:
            logger.error("Bulk index error for %s: %s", index, exc)
            return 0, len(docs)


def build_defillama_pipeline() -> DefiLlamaIngestionPipeline:
    """Factory: create a DefiLlamaIngestionPipeline wired to Elasticsearch."""
    import os
    import sys

    ROOT_DIR = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
    )
    if ROOT_DIR not in sys.path:
        sys.path.insert(0, ROOT_DIR)

    from config.config import Config
    from app.brain.elasticsearch_manager import ElasticsearchManager

    es_manager = ElasticsearchManager(
        Config.ES_URL,
        Config.ES_USERNAME,
        Config.ES_PASSWORD,
        Config.ES_API_KEY_ID,
    )
    return DefiLlamaIngestionPipeline(es_client=es_manager.get_client())
