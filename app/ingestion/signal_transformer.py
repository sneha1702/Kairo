"""
Signal Transformer: maps raw provider rows to the canonical per-signal schema
before any downstream write (Elasticsearch, MongoDB, Gemini).

Responsibilities
----------------
1. Field mapping   – translates provider-specific field names to canonical names.
2. Schema stripping – removes any field not declared in the ES mapping so that
                      strict_dynamic_mapping errors are impossible.
3. Metadata envelope – adds ingested_at, query_name, window_start, etc. (common
                      to every doc regardless of provider).
4. Deterministic _id – collision-free dedup key per signal type.

Adding a new provider
---------------------
1. Add a per-signal mapping function in _TRANSFORMS[provider][query_name].
2. The function receives (raw_row: dict, params: dict) and returns a dict with
   only the canonical fields for that signal (None values are omitted).
3. No changes needed anywhere else — ES mappings, MongoDB, and Gemini are
   unaffected.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.ingestion.base_pipeline import QUERY_TO_SIGNAL, QueryConfig

# ── Canonical field sets (mirrors dune_index_manager._INDEX_MAPPINGS) ─────────
# These are the ONLY fields that may appear in an ES document.
# Metadata fields common to every signal.
_META_FIELDS: set[str] = {
    "ingested_at", "query_name", "signal_category",
    "time_window_hours", "window_start", "params_snapshot",
    "time_bucket", "category", "signals", "signal_count",
}

# Per-signal payload fields.
_SIGNAL_FIELDS: dict[str, set[str]] = {
    "whale_transaction_filter": {
        "block_time", "symbol", "sender", "receiver",
        "token_amount", "usd_value", "total_usd", "whale_usd",
        "smart_money_usd", "tx_hash", "etherscan_url",
    },
    "smart_money_accumulation": {
        "symbol", "smart_money_usd", "whale_usd", "net_flow_usd",
        "smart_money_concentration_pct", "wallet_count",
        "total_smart_money_flow_usd", "wallets_buying_same_token",
    },
    "token_inflow_outflow": {
        "symbol", "from_chain", "to_chain",
        "inflow_tokens", "outflow_tokens",
        "gross_inflow_usd", "gross_outflow_usd", "net_flow_usd",
        "earliest_flow_time", "latest_flow_time",
    },
    "bridge_activity": {
        "symbol", "from_chain", "to_chain", "bridge_name",
        "gross_inflow_usd", "gross_outflow_usd", "bridge_usd",
        "net_flow_usd", "total_usd", "percentage_of_total",
        "tx_count", "acceleration_7d_vs_30d_pct",
    },
    "wallet_concentration": {
        "symbol", "rank", "address", "label", "address_type",
        "balance", "pct_of_supply", "cumulative_pct",
        "whale_concentration_pct", "smart_money_concentration_pct",
        "snapshot_time", "token_address",
    },
    "volume_spike_detection": {
        "symbol", "current_volume_usd", "expected_volume_usd",
        "volume_multiplier", "current_trades", "expected_trades",
        "current_unique_traders", "window_start_time", "window_end_time",
        "acceleration_7d_vs_30d_pct",
    },
    "new_holder_growth": {
        "symbol", "new_wallets", "prior_new_wallets",
        "holder_growth_pct", "total_holders_all_time",
        "first_time_users_pct", "active_addresses",
        "window_start_time", "window_end_time", "token_address",
    },
    "dex_trading_concentration": {
        "symbol", "dex", "pool_volume_usd", "trade_count",
        "unique_traders", "avg_trade_usd", "dex_share_pct",
        "whale_concentration_pct", "volume_multiplier",
        "earliest_trade_time", "latest_trade_time",
    },
    "post_bridge_deployment": {
        "symbol", "chain", "deployment_type", "protocol",
        "net_flow_usd", "total_usd", "percentage_of_total",
        "new_wallets", "tx_count",
    },
    "stablecoin_liquidity_flow": {
        "symbol", "mint_usd", "burn_usd", "net_flow_usd",
        "total_usd", "mint_growth_pct", "new_wallets",
    },
    "ecosystem_sector_rotation": {
        "symbol", "gross_inflow_usd", "gross_outflow_usd",
        "net_flow_usd", "total_usd", "percentage_of_total",
        "trade_count", "unique_traders", "volume_multiplier",
    },
    "protocol_inflow_leaderboard": {
        "symbol", "deployment_type", "net_flow_usd",
        "total_usd", "whale_usd", "new_wallets", "volume_multiplier",
    },
}


def allowed_fields(query_name: str) -> set[str]:
    """Return the complete set of fields allowed for a given signal."""
    return _META_FIELDS | _SIGNAL_FIELDS.get(query_name, set())


# ── DefiLlama field-mapping functions ─────────────────────────────────────────
# Each function receives the raw row dict and the params dict, and returns a
# dict using only canonical field names.  None values are accepted — they are
# filtered out by normalize() so ES never sees a null for a declared field.

def _dl_volume_spike(row: dict, params: dict) -> dict:
    vol = row.get("volume_24h_usd") or 0
    ch  = row.get("change_1d_pct") or 0
    exp = round(vol / (1 + ch / 100), 2) if ch != -100 and vol else None
    mul = round(1 + ch / 100, 4) if ch is not None else None
    end = params.get("end_time")
    tw  = params.get("time_window_hours")
    ws  = None
    if end and tw:
        try:
            end_dt = datetime.fromisoformat(end.replace(" ", "T"))
            ws = (end_dt - timedelta(hours=int(tw))).isoformat()
        except (ValueError, TypeError):
            pass
    return {
        "symbol":                row.get("symbol"),
        "current_volume_usd":    vol or None,
        "expected_volume_usd":   exp,
        "volume_multiplier":     mul,
        "window_start_time":     ws,
        "window_end_time":       end,
    }


def _dl_dex_concentration(row: dict, params: dict) -> dict:
    return {
        "symbol":        row.get("symbol"),
        "dex":           row.get("symbol"),   # protocol name IS the DEX
        "pool_volume_usd": row.get("volume_24h_usd"),
        "dex_share_pct": row.get("market_share_pct"),
    }


def _dl_bridge_activity(row: dict, params: dict) -> dict:
    net  = row.get("net_flow_usd") or 0
    tvl  = row.get("tvl_usd") or 0
    chains: list = row.get("chains") or []
    from_chain = next((c for c in chains if c != "Ethereum"), chains[0] if chains else "Unknown")
    return {
        "symbol":            row.get("bridge_name"),
        "bridge_name":       row.get("bridge_name"),
        "from_chain":        from_chain,
        "to_chain":          "Ethereum",
        "gross_inflow_usd":  round(max(net, 0), 2),
        "gross_outflow_usd": round(max(-net, 0), 2),
        "bridge_usd":        tvl,
        "net_flow_usd":      net,
        "total_usd":         tvl,
    }


def _dl_stablecoin_flow(row: dict, params: dict) -> dict:
    delta = row.get("delta_usd") or 0
    return {
        "symbol":          row.get("symbol"),
        "mint_usd":        round(max(delta, 0), 2),
        "burn_usd":        round(max(-delta, 0), 2),
        "net_flow_usd":    delta,
        "total_usd":       row.get("circulating_usd"),
        "mint_growth_pct": row.get("change_pct"),
    }


def _dl_sector_rotation(row: dict, params: dict) -> dict:
    tvl      = row.get("tvl_usd") or 0
    tvl_prev = row.get("tvl_prev_usd") or 0
    net      = tvl - tvl_prev
    mul      = round(tvl / tvl_prev, 4) if tvl_prev else None
    return {
        "symbol":            row.get("category"),
        "gross_inflow_usd":  round(max(net, 0), 2),
        "gross_outflow_usd": round(max(-net, 0), 2),
        "net_flow_usd":      round(net, 2),
        "total_usd":         tvl,
        "trade_count":       row.get("protocol_count"),
        "volume_multiplier": mul,
    }


def _dl_protocol_inflow(row: dict, params: dict) -> dict:
    return {
        "symbol":            row.get("symbol"),
        "deployment_type":   "tvl_proxy",
        "net_flow_usd":      row.get("net_flow_usd"),
        "total_usd":         row.get("tvl_usd"),
        "volume_multiplier": row.get("volume_multiplier"),
    }


# Dispatch table for DefiLlama transforms
_DEFILLAMA_MAP: dict[str, Any] = {
    "volume_spike_detection":      _dl_volume_spike,
    "dex_trading_concentration":   _dl_dex_concentration,
    "bridge_activity":             _dl_bridge_activity,
    "stablecoin_liquidity_flow":   _dl_stablecoin_flow,
    "ecosystem_sector_rotation":   _dl_sector_rotation,
    "protocol_inflow_leaderboard": _dl_protocol_inflow,
}

# ── Timestamp normalization ────────────────────────────────────────────────────
_TS_UTC  = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}(?:\.\d+)?) UTC$")
_TS_BARE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}(?:\.\d+)?)$")


def _fix_timestamps(doc: dict) -> dict:
    for k, v in list(doc.items()):
        if isinstance(v, str):
            m = _TS_UTC.match(v)
            if m:
                doc[k] = f"{m.group(1)}T{m.group(2)}Z"
                continue
            m = _TS_BARE.match(v)
            if m:
                doc[k] = f"{m.group(1)}T{m.group(2)}"
    return doc


# ── Metadata envelope ──────────────────────────────────────────────────────────

def _build_metadata(qc: QueryConfig, ingested_at: datetime) -> dict:
    end_raw = qc.params.get("end_time")
    tw = qc.params.get("time_window_hours")
    if end_raw:
        try:
            end_dt = datetime.fromisoformat(end_raw.replace(" ", "T"))
            if not end_dt.tzinfo:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            end_dt = ingested_at
    else:
        end_dt = ingested_at

    window_start = (
        (end_dt - timedelta(hours=int(tw))).isoformat()
        if tw is not None else None
    )
    return {
        "ingested_at":       ingested_at.isoformat(),
        "query_name":        qc.query_name,
        "signal_category":   qc.signal_category or QUERY_TO_SIGNAL.get(qc.query_name, ""),
        "time_window_hours": int(tw) if tw is not None else None,
        "window_start":      window_start,
        "params_snapshot":   dict(qc.params),
        "time_bucket":       end_raw or ingested_at.strftime("%Y-%m-%d %H:%M:%S"),
        "category":          qc.signal_category or QUERY_TO_SIGNAL.get(qc.query_name, ""),
    }


# ── Deterministic _id ──────────────────────────────────────────────────────────

def _make_id(query_name: str, provider: str, doc: dict, qc: QueryConfig, ingested_at: datetime) -> str:
    end_raw = qc.params.get("end_time")
    tw = qc.params.get("time_window_hours")
    if end_raw:
        try:
            end_dt = datetime.fromisoformat(end_raw.replace(" ", "T"))
            if not end_dt.tzinfo:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            end_dt = ingested_at
    else:
        end_dt = ingested_at

    if tw is not None:
        ws = (end_dt - timedelta(hours=int(tw))).replace(
            minute=0, second=0, microsecond=0
        ).isoformat()
    else:
        ws = end_dt.strftime("%Y-%m-%d")

    name = query_name
    if name == "whale_transaction_filter":
        parts = [provider, str(doc.get("tx_hash", ""))]
    elif name in ("smart_money_accumulation", "token_inflow_outflow",
                  "volume_spike_detection", "new_holder_growth",
                  "stablecoin_liquidity_flow", "ecosystem_sector_rotation"):
        parts = [provider, str(doc.get("symbol", "")), ws]
    elif name == "bridge_activity":
        parts = [provider, str(doc.get("symbol", "")), str(doc.get("bridge_name", "")), ws]
    elif name == "wallet_concentration":
        parts = [provider, str(qc.params.get("token_address", "")), str(doc.get("address", "")), ws]
    elif name == "dex_trading_concentration":
        parts = [provider, str(doc.get("symbol", "")), str(doc.get("dex", "")), ws]
    elif name in ("post_bridge_deployment", "protocol_inflow_leaderboard"):
        parts = [provider, str(doc.get("symbol", "")), str(doc.get("deployment_type", "")), ws]
    else:
        parts = [provider, name, ws]

    return hashlib.sha256("||".join(parts).encode()).hexdigest()[:24]


# ── Public API ─────────────────────────────────────────────────────────────────

def normalize(
    query_name: str,
    provider: str,
    raw_rows: list[dict],
    qc: QueryConfig,
    ingested_at: datetime | None = None,
) -> list[dict]:
    """
    Transform *raw_rows* from *provider* into canonical ES-ready documents.

    Returns a list of dicts, each containing:
    - Only fields declared for the signal (strict schema compliance)
    - Metadata envelope (ingested_at, query_name, window_start, …)
    - A ``_id`` key for deterministic ES document ID
    """
    if ingested_at is None:
        ingested_at = datetime.now(timezone.utc)

    mapper = _DEFILLAMA_MAP.get(query_name) if provider == "defillama" else None
    meta   = _build_metadata(qc, ingested_at)
    allowed = allowed_fields(query_name)
    docs: list[dict] = []

    for row in raw_rows:
        if mapper is not None:
            # DefiLlama: map raw row to canonical field names first
            payload = mapper(row, qc.params)
            # Preserve signal fields from the raw row (time_bucket, signals, signal_count)
            for f in ("time_bucket", "category", "signals", "signal_count"):
                if f in row and f not in payload:
                    payload[f] = row[f]
        else:
            # Dune (and future providers that already output canonical names)
            payload = dict(row)

        # Merge metadata; row values take precedence for shared keys (e.g. time_bucket)
        doc = {**meta, **payload}

        # Fix timestamp format (Dune returns "YYYY-MM-DD HH:MM:SS UTC")
        doc = _fix_timestamps(doc)

        # Strip to schema — eliminate any field ES doesn't know about
        doc = {k: v for k, v in doc.items() if k in allowed and v is not None}

        doc["_id"] = _make_id(query_name, provider, doc, qc, ingested_at)
        docs.append(doc)

    return docs
