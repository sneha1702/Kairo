"""
Narrative Engine: Detects and analyzes emerging crypto narratives from on-chain signals.
Uses Gemini to infer narratives from Dune Analytics data (8 signal types) plus whale activity.
"""

import json
import logging
import os
from google import genai
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from collections import defaultdict

logger = logging.getLogger(__name__)

_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


# ── .env loading (optional) ────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass



class NarrativeEngine:
    def __init__(self, gemini_api_key: str):
        from config.config import Config
        project      = Config.GOOGLE_CLOUD_PROJECT
        location     = Config.GOOGLE_CLOUD_LOCATION
        model_name   = Config.GEMINI_MODEL
        self.client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )
        self.model_name = model_name

    # ── Legacy whale grouping (kept for backward compat) ──────────────────────

    def group_whale_activity(self, transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Group whale transactions by category and time window."""
        df = pd.DataFrame(transactions)
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        category_groups: Dict[str, Any] = defaultdict(lambda: {
            "total_volume_usd": 0,
            "tx_count": 0,
            "tokens": set(),
            "wallets": set(),
            "buy_volume": 0,
            "sell_volume": 0,
            "recent_activity": [],
        })

        for _, row in df.iterrows():
            cat = row.get("category", "Unknown")
            category_groups[cat]["total_volume_usd"] += row.get("amount_usd", 0)
            category_groups[cat]["tx_count"] += 1
            category_groups[cat]["tokens"].add(row.get("token"))
            category_groups[cat]["wallets"].add(row.get("wallet"))
            if row.get("action") == "BUY":
                category_groups[cat]["buy_volume"] += row.get("amount_usd", 0)
            else:
                category_groups[cat]["sell_volume"] += row.get("amount_usd", 0)
            category_groups[cat]["recent_activity"].append({
                "token": row.get("token"),
                "action": row.get("action"),
                "amount": row.get("amount_usd"),
                "wallet": row.get("wallet"),
                "timestamp": row["timestamp"].isoformat(),
            })

        return {
            cat: {
                **data,
                "tokens": list(data["tokens"]),
                "wallets": list(data["wallets"]),
                "buy_sell_ratio": data["buy_volume"] / max(data["sell_volume"], 1),
                "recent_activity": sorted(
                    data["recent_activity"], key=lambda x: x["timestamp"], reverse=True
                )[:5],
            }
            for cat, data in category_groups.items()
        }

    # ── Dune signal summary ────────────────────────────────────────────────────

    def build_signal_summary(self, dune_context: Dict[str, Any]) -> Dict[str, Any]:
        """Condense the 8 Dune signal buckets into a concise summary for the prompt."""

        def _num(val: Any) -> float:
            try:
                return float(val)
            except (TypeError, ValueError):
                return 0.0

        summary: Dict[str, Any] = {}

        smart_money = dune_context.get("smart_money", [])
        if smart_money:
            top_sm = sorted(smart_money, key=lambda x: _num(x.get("total_bought_usd")), reverse=True)[:5]
            summary["smart_money"] = {
                "wallet_min100K_buy_count": sum({r.get("buy_count") for r in smart_money}),
                "top_buys": [
                    {
                        "symbol":     r.get("symbol"),                        
                        "signal":     r.get("accumulation_signal"),
                        "first_buy":  r.get("first_buy"),
                        "last_buy":   r.get("last_buy"),
                        "usd":        r.get("total_bought_usd"),
                    }
                    for r in top_sm
                ],
                "total_flow_usd": _num(next(
                    (r.get("total_smart_money_flow_usd") for r in smart_money if r.get("total_smart_money_flow_usd") is not None),
                    0
                )),
                "other_wallets_buying_same_token": _num(next(
                    (r.get("wallets_buying_same_token") for r in smart_money if r.get("wallets_buying_same_token") is not None),
                    0
                )),
                "time_span_hours": _num(next(
                    (r.get("time_window_hours") for r in smart_money if r.get("time_window_hours") is not None),
                    0
                )),
                "ingested_at": next(
                    (r.get("ingested_at") for r in smart_money if r.get("ingested_at") is not None),
                    None
                )
            }

        token_flows = dune_context.get("token_flows", [])
        if token_flows:
            top_inflow = sorted(token_flows, key=lambda x: _num(x.get("net_flow_usd")), reverse=True)[:5]
            summary["token_flows"] = {
                "top_inflows": [
                    {
                        "token":              r.get("token"),
                        "inflow_usd":       r.get("inflow_usd"),
                        "outflow_usd":       r.get("outflow_usd"),
                        "net_flow_usd":       r.get("net_flow_usd"),
                        "signal":             r.get("signal"),
                        "earliest_flow_time": r.get("window_start"),
                        "latest_flow_time":   r.get("ingested_at"),
                    }
                    for r in top_inflow
                ],
                "time_span_hours": _num(next(
                    (r.get("time_window_hours") for r in smart_money if r.get("time_window_hours") is not None),
                    0
                )),
                "ingested_at": next(
                    (r.get("ingested_at") for r in smart_money if r.get("ingested_at") is not None),
                    None
                ) 
            }
            
           

        bridges = dune_context.get("bridge_activity", [])
        if bridges:
            summary["bridge_activity"] = {
                "total_usd": sum(_num(r.get("total_usd")) for r in bridges),
                "top_routes": [
                    {
                        "direction":        r.get("direction"),
                        "bridge":           r.get("bridge"),
                        "usd":              r.get("total_usd"),
                        "signal":           r.get("capital_signal"),
                        "earliest_tx_time": r.get("earliest_tx_time"),
                        "latest_tx_time":   r.get("latest_tx_time"),
                    }
                    for r in sorted(bridges, key=lambda x: _num(x.get("total_usd")), reverse=True)[:4]
                ],
            }

        spikes = dune_context.get("volume_spikes", [])
        if spikes:
            summary["volume_spikes"] = [
                {
                    "symbol":           r.get("symbol"),
                    "multiplier":       r.get("volume_multiplier"),
                    "signal":           r.get("spike_signal"),
                    "window_start_time": r.get("window_start_time"),
                    "window_end_time":   r.get("window_end_time"),
                }
                for r in sorted(spikes, key=lambda x: _num(x.get("volume_multiplier")), reverse=True)[:5]
            ]

        holder = dune_context.get("holder_growth", [])
        if holder:
            summary["holder_growth"] = [
                {
                    "token_address":    r.get("token_address"),
                    "growth_rate_pct":  r.get("growth_rate_pct"),
                    "signal":           r.get("growth_signal"),
                    "window_start_time": r.get("window_start_time"),
                    "window_end_time":   r.get("window_end_time"),
                }
                for r in sorted(holder, key=lambda x: _num(x.get("growth_rate_pct")), reverse=True)[:5]
            ]

        dex = dune_context.get("dex_concentration", [])
        if dex:
            summary["dex_concentration"] = [
                {
                    "symbol":               r.get("symbol"),
                    "dex":                  r.get("dex"),
                    "dex_share_pct":        r.get("dex_share_pct"),
                    "signal":               r.get("concentration_signal"),
                    "earliest_trade_time":  r.get("earliest_trade_time"),
                    "latest_trade_time":    r.get("latest_trade_time"),
                }
                for r in sorted(dex, key=lambda x: _num(x.get("pool_volume_usd")), reverse=True)[:5]
            ]

        whale_txs = dune_context.get("whale_transactions", [])
        if whale_txs:
            top_whales = sorted(whale_txs, key=lambda x: _num(x.get("usd_value")), reverse=True)[:5]
            summary["whale_transactions"] = {
                "count": len(whale_txs),
                "total_usd": sum(_num(r.get("usd_value")) for r in whale_txs),
                "top_symbols": list({r.get("symbol") for r in whale_txs if r.get("symbol")})[:5],
                "top_txs": [
                    {
                        "symbol":     r.get("symbol"),
                        "usd_value":  r.get("usd_value"),
                        "block_time": r.get("block_time"),
                        "sender":     (r.get("sender") or "")[:12] + "…" if r.get("sender") else None,
                        "receiver":   (r.get("receiver") or "")[:12] + "…" if r.get("receiver") else None,
                    }
                    for r in top_whales
                ],
            }

        wallet_conc = dune_context.get("wallet_concentration", [])
        if wallet_conc:
            top10 = [r for r in wallet_conc if r.get("rank", 999) <= 10]
            summary["wallet_concentration"] = {
                "top10_cumulative_pct": max(
                    (_num(r.get("cumulative_pct")) for r in top10), default=0.0
                ),
                "sample": [
                    {
                        "rank":          r.get("rank"),
                        "pct_of_supply": r.get("pct_of_supply"),
                        "snapshot_time": r.get("snapshot_time"),
                    }
                    for r in top10[:3]
                ],
            }

        return summary

    # ── Cross-signal token confluence ──────────────────────────────────────────

    def build_token_confluence(self, dune_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Pivot signal data from per-signal-type → per-token.
        Returns tokens ranked by number of independent signals confirming them,
        so Gemini can instantly see which assets have multi-signal conviction.
        """
        def _num(v: Any) -> float:
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        # token → accumulated metrics across all signal types
        tokens: Dict[str, Dict[str, Any]] = {}

        def _touch(sym: str) -> Dict[str, Any]:
            if not sym:
                return {}
            sym = sym.upper().strip()
            if sym not in tokens:
                tokens[sym] = {
                    "symbol": sym, "signals": [], "signal_count": 0,
                    "total_usd": 0.0, "smart_money_usd": 0.0,
                    "whale_usd": 0.0, "volume_multiplier": 0.0,
                    "net_flow_usd": 0.0, "bridge_usd": 0.0,
                    "holder_growth_pct": 0.0, "dex_share_pct": 0.0,
                }
            return tokens[sym]

        def _add_signal(sym: str, signal_name: str) -> None:
            t = _touch(sym)
            if t and signal_name not in t["signals"]:
                t["signals"].append(signal_name)
                t["signal_count"] += 1

        for rec in dune_context.get("smart_money", []):
            sym = rec.get("symbol", "")
            if sym:
                t = _touch(sym)
                usd = _num(rec.get("total_bought_usd"))
                t["smart_money_usd"] += usd
                t["total_usd"] += usd
                _add_signal(sym, "smart_money")

        for rec in dune_context.get("whale_transactions", []):
            sym = rec.get("symbol", "")
            if sym:
                t = _touch(sym)
                usd = _num(rec.get("usd_value"))
                t["whale_usd"] += usd
                t["total_usd"] += usd
                _add_signal(sym, "whale_transactions")

        for rec in dune_context.get("volume_spikes", []):
            sym = rec.get("symbol", "")
            if sym:
                t = _touch(sym)
                mult = _num(rec.get("volume_multiplier"))
                if mult > t["volume_multiplier"]:
                    t["volume_multiplier"] = mult
                _add_signal(sym, "volume_spikes")

        for rec in dune_context.get("token_flows", []):
            tok = rec.get("token", "")
            if tok:
                t = _touch(tok)
                t["net_flow_usd"] += _num(rec.get("net_flow_usd"))
                _add_signal(tok, "token_flows")

        for rec in dune_context.get("bridge_activity", []):
            # bridge records don't have a single token, use direction as label
            direction = rec.get("direction", "")
            bridge = rec.get("bridge", "")
            label = f"{bridge}:{direction}" if bridge else direction
            if label:
                t = _touch(label)
                usd = _num(rec.get("total_usd"))
                t["bridge_usd"] += usd
                t["total_usd"] += usd
                _add_signal(label, "bridge_activity")

        for rec in dune_context.get("holder_growth", []):
            tok = rec.get("token_address", "")
            if tok:
                t = _touch(tok)
                g = _num(rec.get("growth_rate_pct"))
                if g > t["holder_growth_pct"]:
                    t["holder_growth_pct"] = g
                _add_signal(tok, "holder_growth")

        for rec in dune_context.get("dex_concentration", []):
            sym = rec.get("symbol", "")
            if sym:
                t = _touch(sym)
                share = _num(rec.get("dex_share_pct"))
                if share > t["dex_share_pct"]:
                    t["dex_share_pct"] = share
                _add_signal(sym, "dex_concentration")

        # Round floats and rank by signal_count then total_usd
        result = sorted(tokens.values(), key=lambda x: (-x["signal_count"], -x["total_usd"]))
        for t in result:
            for k in ("total_usd", "smart_money_usd", "whale_usd", "net_flow_usd", "bridge_usd"):
                t[k] = round(t[k], 0)
            t["volume_multiplier"] = round(t["volume_multiplier"], 2)
            t["holder_growth_pct"] = round(t["holder_growth_pct"], 2)
            t["dex_share_pct"]     = round(t["dex_share_pct"], 2)
        return result[:20]  # top 20 tokens by conviction

    # ── Per-token evidence timestamp extraction ────────────────────────────────

    @staticmethod
    def _build_evidence_timestamps(narrative: Dict, dune_context: Dict) -> Dict:
        """
        For each of the narrative's top_tokens, collect the individual on-chain
        timestamps from dune_context so MongoDB preserves full lineage:
        when each whale tx was placed, when smart money first/last bought, etc.
        """
        top_tokens = {t.upper() for t in (narrative.get("top_tokens") or [])}
        if not top_tokens or not dune_context:
            return {}

        result: Dict[str, Any] = {}

        def _sym(rec: Dict, *keys: str) -> str:
            for k in keys:
                v = rec.get(k)
                if v:
                    return str(v).upper()
            return ""

        for tok in top_tokens:
            entry: Dict[str, Any] = {}

            whale_times = sorted(
                {r.get("block_time") for r in dune_context.get("whale_transactions", [])
                 if _sym(r, "symbol") == tok and r.get("block_time")}
            )
            if whale_times:
                entry["whale_tx_block_times"] = whale_times[:10]

            sm = [r for r in dune_context.get("smart_money", []) if _sym(r, "symbol") == tok]
            if sm:
                first_buys = [r.get("first_buy") for r in sm if r.get("first_buy")]
                last_buys  = [r.get("last_buy")  for r in sm if r.get("last_buy")]
                if first_buys:
                    entry["smart_money_first_buy"] = min(first_buys)
                if last_buys:
                    entry["smart_money_last_buy"] = max(last_buys)

            sp = [r for r in dune_context.get("volume_spikes", []) if _sym(r, "symbol") == tok]
            if sp:
                entry["volume_spike_window_start"] = sp[0].get("window_start_time")
                entry["volume_spike_window_end"]   = sp[0].get("window_end_time")

            tf = [r for r in dune_context.get("token_flows", [])
                  if _sym(r, "token") == tok]
            if tf:
                entry["flow_earliest"] = min((r.get("earliest_flow_time") for r in tf if r.get("earliest_flow_time")), default=None)
                entry["flow_latest"]   = max((r.get("latest_flow_time")   for r in tf if r.get("latest_flow_time")),   default=None)

            if entry:
                result[tok] = entry

        # Bridge flows are not token-specific; store global window for the narrative
        bridges = dune_context.get("bridge_activity", [])
        if bridges:
            b_starts = [r.get("earliest_tx_time") for r in bridges if r.get("earliest_tx_time")]
            b_ends   = [r.get("latest_tx_time")   for r in bridges if r.get("latest_tx_time")]
            if b_starts:
                result["_bridge_earliest_tx"] = min(b_starts)
            if b_ends:
                result["_bridge_latest_tx"] = max(b_ends)

        return result

    # ── Core detection ─────────────────────────────────────────────────────────

    def detect_narratives(
        self,
        whale_activity: Optional[Dict[str, Any]] = None,
        historical_narratives: Optional[List[Dict]] = None,
        dune_context: Optional[Dict[str, Any]] = None,
        signal_trend: Optional[List[Dict]] = None,
        unified_signals: Optional[List[Dict]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Use Gemini to detect and evolve narratives.
        Accepts legacy whale_activity dict and/or the full 8-signal dune_context.
        signal_trend: list of per-bucket aggregate metrics for temporal acceleration view.
        """
        def _default(obj: Any) -> str:
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Not serializable: {type(obj)}")

        # ── Section 2: narrative history ───────────────────────────────────────
        history_section = "None yet — this may be the first run."
        if historical_narratives:
            slim = [
                {
                    "narrative_id":       n.get("narrative_id", ""),
                    "name":               n.get("name", ""),
                    "category":           n.get("category", ""),
                    "status":             n.get("status", ""),
                    "confidence_score":   n.get("confidence_score", 0),
                    "strength":           n.get("strength", ""),
                    "top_tokens":         n.get("top_tokens", []),
                    "key_evidence":       (n.get("key_evidence") or [])[:3],
                    "signal_sources":     n.get("signal_sources", []),
                    "momentum_trend":     (n.get("momentum") or {}).get("trend", ""),
                    "hours_since_update": n.get("hours_since_update"),
                    "detected_at":        n.get("detected_at", ""),
                }
                for n in historical_narratives
            ]
            history_section = json.dumps(slim, indent=2, default=_default)

        # ── Data provenance — derived from unified_signals or dune_context ─────
        data_window_start: Optional[str] = None
        data_window_end:   Optional[str] = None
        last_ingested_at:  Optional[str] = None

        if unified_signals:
            buckets = [s["time_bucket"] for s in unified_signals if s.get("time_bucket")]
            if buckets:
                data_window_start = min(buckets)
                data_window_end   = max(buckets)

        if dune_context:
            all_ingested_ats: List[str] = []
            for docs in dune_context.values():
                for doc in docs:
                    ia = doc.get("ingested_at")
                    if ia and isinstance(ia, str):
                        all_ingested_ats.append(ia)
            if all_ingested_ats:
                last_ingested_at = max(all_ingested_ats)

        data_freshness_header = (
            f"Signal window: {data_window_start} → {data_window_end}"
            + (f" | last ingested at {last_ingested_at}" if last_ingested_at else "")
            + f" | prompt built at {datetime.utcnow().isoformat()}Z"
        )

        # ── Unified signals section (sole data input to the prompt) ────────────
        if unified_signals:
            unified_section = json.dumps(unified_signals, indent=2, default=_default)
            single_day_only = (
                len({s["time_bucket"] for s in unified_signals if s.get("time_bucket")}) <= 1
            )
        else:
            unified_section  = "No signal data available for this window."
            single_day_only  = True

        confidence_cap_note = (
            "NOTE: All signals cover a single day only — cap confidence at 0.74 and flag in data_caveat."
            if single_day_only else ""
        )

        prompt = f"""You are a crypto narrative intelligence analyst writing **plain-English investor briefings**.

Your output is NOT a dashboard, NOT a data report, and NOT a technical analysis sheet.
It is a morning briefing that explains what is happening in crypto markets, why it matters, and what might happen next — written for a smart but non-technical retail investor.

Think: *"Financial news explainer for someone who knows what Bitcoin is but has never used a crypto app."*

════════════════════════════════════════════════════════
CORE RULES (NON-NEGOTIABLE)
════════════════════════════════════════════════════════

RULE 1: Every narrative must be anchored in real numbers from Section 3.
RULE 2: Write for a non-technical retail investor — no unexplained jargon or acronyms.
RULE 3: A narrative is a sustained market theme that develops over days, NOT a single token event.
RULE 4: Explain what is happening and why it matters — not how the data system works.
RULE 5: Output is upserted into MongoDB using narrative_id as the key.
RULE 6: Do NOT output dashboards, rankings, or analytical commentary. Only investor briefings.
RULE 7: Prefer narrative continuity — merge evidence into existing stories rather than creating new ones.

════════════════════════════════════════════════════════
SECTION 1 — CANONICAL NARRATIVE IDs
════════════════════════════════════════════════════════

Prefer these stable identifiers before inventing new ones:

  ai_infrastructure          ethereum_staking
  ai_agents                  gaming_ecosystem
  defi_lending               memecoin_speculation
  defi_yield                 cross_chain_liquidity
  defi_bluechip              institutional_bitcoin
  layer2_scaling             institutional_ethereum
  l2_capital_rotation        stablecoin_accumulation
  real_world_assets          bridge_capital_rotation

If none fits, create a new snake_case id (e.g. "solana_defi_revival").

════════════════════════════════════════════════════════
SECTION 2 — EXISTING NARRATIVES (prior state)
════════════════════════════════════════════════════════

{history_section}

Each entry shows: narrative_id, prior key_evidence, prior signal_sources, momentum_trend, hours_since_update.

CONTINUITY RULES:
  • ALWAYS prefer updating an existing narrative over creating a new one for the same theme.
  • Merge new evidence into the existing story arc — write it as a "live briefing update", not a new report.
  • Only create a new narrative_id if no existing one covers the theme AND signal_count ≥ 2.
  • Do NOT fragment one theme into multiple small narratives.

════════════════════════════════════════════════════════
SECTION 3 — ON-CHAIN SIGNAL DATA (sole data input)
════════════════════════════════════════════════════════

{data_freshness_header}
{confidence_cap_note}

TREAT THIS AS RAW FACTS ONLY. Do NOT interpret here — interpretation belongs in the narrative output fields.

{unified_section}

── Field guide ──────────────────────────────────────────

capital_migration records capture money moving between blockchains:
  • symbol              — which token is moving (e.g. WETH, USDC)
  • from_chain / to_chain — source and destination blockchain
  • total_usd           — combined dollar value of all cross-chain movement
  • bridge_usd          — portion that crossed via a bridge protocol
  • net_flow_usd        — net direction of token flow (positive = net inflow to destination)
  • whale_concentration_pct — how much of this token the largest holders control (0–100)
  • acceleration_7d_vs_30d_pct — how much faster capital is moving this week vs. the 30-day daily average
  • signal_count        — number of independent signal types confirming this movement (higher = more conviction)

smart_deployment records capture experienced investors putting money to work:
  • smart_money_usd     — dollar value deployed by wallets with strong historical track records
  • deployment_type     — how the money is being deployed (e.g. lending, liquidity, staking)
  • protocol            — the specific platform receiving the capital

stablecoin_flow records capture fresh buying power entering the market:
  • net_flow_usd        — net direction of stablecoin movement
  • mint_usd            — new stablecoins created (proxy for fresh capital entering crypto)

── Data quality rules ───────────────────────────────────

  • If a field is 0 or absent, do NOT cite it as evidence.
  • net_flow_usd = 0 does NOT confirm accumulation — treat it as no signal.
  • top_tokens must be token symbols (ETH, USDC, WBTC) — never chain names.
  • signal_count is a confidence proxy, NOT a narrative definition.

════════════════════════════════════════════════════════
SECTION 4 — EVOLUTION SCENARIOS
════════════════════════════════════════════════════════

SCENARIO A — CONTINUING / ACCELERATING
  Condition: A theme in Section 3 matches an existing narrative_id in Section 2.
  Action: Reuse the same narrative_id. Set status=CONTINUING or ACCELERATING.
          Add new observations to key_evidence — do not repeat prior evidence.
          Update confidence based on fresh signals. Update top_tokens if changed.

SCENARIO B — NEW NARRATIVE
  Condition: A theme in Section 3 has signal_count ≥ 2 AND no match in Section 2.
  Action: Create a new narrative_id. Set status=NEW.
          The narrative must represent a real-world investor story, not a token cluster.

SCENARIO C — STABLE / STAGNATING
  Condition: An existing narrative_id has NO matching signals in Section 3,
             AND hours_since_update < 72.
  Action: STILL RETURN IT. Set status=STABLE, reduce confidence slightly.
          This keeps valid multi-day themes alive through quiet data cycles.

Evidence → confidence mapping (STRICTLY enforce):
  • signal_count ≥ 3 + acceleration        → confidence 0.75–0.85
  • signal_count ≥ 3, no acceleration      → confidence 0.70–0.79
  • signal_count = 2                       → confidence 0.55–0.69
  • signal_count = 1, volume > $50M        → confidence 0.40–0.54
  • signal_count = 1, bridge only          → confidence max 0.50
  • Single-day data only                   → cap at 0.74, note in data_caveat

DO NOT return narratives with confidence_score < 0.40.
DO NOT fabricate signal evidence not present in Section 3.

════════════════════════════════════════════════════════
SECTION 5 — WRITING STYLE (investor briefing rules)
════════════════════════════════════════════════════════

You are writing a retail investor briefing, not a data system output.

RULES:

1. Translate every signal into plain-English meaning:
   NEVER write:  "whale_usd increased in token_flows metric"
   ALWAYS write: "Large investors moved about $X into [token]"

   Signal translations:
     smart_money       → "experienced large investors" or "wallets with a strong track record"
     bridge_activity   → "money moving between blockchains" or "capital rotating into [chain]"
     whale_transactions→ "very large holders shifting funds" (typically $500K or more per move)
     stablecoin_mint   → "fresh buying power entering the market" or "new dollars arriving in crypto"

2. Every narrative must answer four questions in plain English:
   • What is happening right now?
   • Who is moving money (what type of investor)?
   • Why does it matter for the broader market?
   • What could happen next?

3. Context all dollar amounts with a size anchor:
   "$1.2B" → "$1.2 billion — roughly the size of a mid-sized investment fund"
   "$50M"  → "about $50 million, a significant single-day institutional move"

4. No jargon without an immediate explanation in parentheses on first use:
   OK: "decentralized exchanges (platforms where people trade crypto directly)"
   NOT OK: "DEX volume spiked"

5. FORBIDDEN in output text fields (implications, summary, retail_considerations):
   "signal_count" • "confluence" • "dex concentration" • "net outflow" • "on-chain"
   "L1" • "L2" • "CEX" • "net flow" • "token_flows" • "whale_usd"
   If you need to express these concepts, use the plain-English equivalents above.

6. plain_english_summary: exactly 2 sentences, texting-a-friend style:
   "Big money wallets are quietly moving funds into Ethereum. This kind of positioning
    has historically preceded price moves, but there's no guarantee it will this time."

7. retail_considerations: exactly 3 parts:
   (1) What this means for regular investors in plain English
   (2) One specific thing to watch as a signal of continuation or reversal
   (3) A clear risk reminder: "On-chain movements are early signals that can reverse quickly —
       this is not financial advice."

════════════════════════════════════════════════════════
SECTION 6 — OUTPUT FORMAT
════════════════════════════════════════════════════════

Return ONLY a valid JSON array — no markdown, no prose, no explanation outside the array.
Maximum 5 narratives. Always include Scenario C narratives if hours_since_update < 72.

Each object MUST have EXACTLY these fields:

{{
  "narrative_id":          "snake_case_stable_id",
  "name":                  "Investor-briefing title — plain English, no acronyms (e.g. 'Big Money Rotating Into Ethereum')",
  "category":              "AI | DeFi | L2 | RWA | Stablecoins | Infrastructure | Gaming | NFT | Memecoin | CrossChain | Institutional | Other",
  "status":                "NEW | CONTINUING | ACCELERATING | REVERSING | STABLE",
  "strength":              "High | Medium | Low",
  "momentum":              "Strengthening | Stable | Weakening",
  "confidence_score":      0.0,
  "key_evidence":          [
    "Data citation in plain English with real numbers — e.g. 'About $125M moved from Ethereum to Base via bridges, running 2.4x faster than the 30-day average'"
  ],
  "data_caveat":           "Simple explanation of limitations — e.g. 'Only 24 hours of data available, so this may be an early signal rather than a confirmed trend'",
  "historical_context":    "One sentence on continuity — if NEW say 'First detection with only 24h of data; no multi-day trend yet confirmed.' If CONTINUING, compare to prior detection.",
  "implications":          "2–3 plain-English sentences: what could this mean for markets next? No jargon.",
  "plain_english_summary": "Exactly 2 sentences — what is happening + why it might matter. Texting-a-friend tone.",
  "top_tokens":            ["TOKEN_SYMBOL_ONLY — e.g. USDC, ETH, WBTC — never chain names"],
  "retail_considerations": "Three clearly separated parts: (1) plain-English meaning for regular investors, (2) one specific thing to watch, (3) risk reminder.",
  "signal_sources":        ["bridge_activity", "smart_money"]
}}

════════════════════════════════════════════════════════
FINAL RULE
════════════════════════════════════════════════════════

If there is any conflict between data precision and investor clarity:
PRIORITIZE HUMAN CLARITY AND INVESTOR UNDERSTANDING OVER TECHNICAL PRECISION.

A narrative that a non-crypto person can understand and act on is always better than
a technically accurate one they cannot follow.
"""

        # ── Save prompt to disk ────────────────────────────────────────────────
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            _PROMPT_DIR.mkdir(parents=True, exist_ok=True)
            prompt_file = _PROMPT_DIR / f"prompt_{ts}.txt"
            prompt_file.write_text(prompt, encoding="utf-8")
            logger.info("[GEMINI] Prompt saved → %s (%d chars)", prompt_file, len(prompt))
        except Exception as exc:
            logger.warning("[GEMINI] Could not save prompt: %s", exc)

        logger.info("[GEMINI] Sending request to %s", self.model_name)
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
        )
        raw_response = getattr(response, "text", "") or ""
        logger.info("[GEMINI] Response received — %d chars", len(raw_response))

        # ── Save raw Gemini response alongside the prompt ──────────────────────
        try:
            response_file = _PROMPT_DIR / f"response_{ts}.txt"
            response_file.write_text(raw_response, encoding="utf-8")
            logger.info("[GEMINI] Response saved  → %s", response_file)
        except Exception as exc:
            logger.warning("[GEMINI] Could not save response: %s", exc)

        try:
            response_text = raw_response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]

            narratives = json.loads(response_text)
            logger.info("[GEMINI] Parsed %d narratives from response", len(narratives))

            built_at = datetime.utcnow().isoformat() + "Z"
            for narrative in narratives:
                narrative["detected_at"]        = built_at
                narrative["source"]             = "gemini_analysis"
                narrative["data_window_start"]  = data_window_start
                narrative["data_window_end"]    = data_window_end
                narrative["last_ingested_at"]   = last_ingested_at
                narrative["prompt_built_at"]    = built_at
                narrative["evidence_timestamps"] = self._build_evidence_timestamps(
                    narrative, dune_context or {}
                )

            return narratives
        except json.JSONDecodeError as e:
            logger.error("[GEMINI] Failed to parse response JSON: %s", e)
            logger.debug("[GEMINI] Raw response: %s", raw_response)
            return []

    # ── Momentum ───────────────────────────────────────────────────────────────

    def calculate_narrative_momentum(
        self, current_narrative: Dict, previous_narratives: List[Dict]
    ) -> Dict:
        if not previous_narratives:
            return {"trend": "new", "momentum_score": 0.5, "strength_change": 0, "confidence_change": 0}

        current_id = (current_narrative.get("narrative_id") or "").strip()
        matching_previous = None
        for prev in sorted(previous_narratives, key=lambda x: x.get("detected_at", ""), reverse=True)[:5]:
            if (prev.get("narrative_id") or "").strip() == current_id and current_id:
                matching_previous = prev
                break

        if not matching_previous:
            return {
                "trend": "emerging",
                "momentum_score": current_narrative.get("confidence_score", 0.5),
                "strength_change": 0,
                "confidence_change": 0,
            }

        confidence_change = (
            current_narrative.get("confidence_score", 0) - matching_previous.get("confidence_score", 0)
        )
        strength_map = {"High": 3, "Medium": 2, "Low": 1}
        strength_change = strength_map.get(
            current_narrative.get("strength") or "Medium", 2
        ) - strength_map.get(matching_previous.get("strength") or "Medium", 2)

        if confidence_change > 0.1 or strength_change > 0:
            trend = "strengthening"
        elif confidence_change < -0.1 or strength_change < 0:
            trend = "weakening"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "momentum_score": min(1.0, max(0.0, 0.5 + (confidence_change / 2))),
            "strength_change": strength_change,
            "confidence_change": confidence_change,
        }

    def enrich_narrative(
        self, narrative: Dict, previous_narratives: Optional[List[Dict]] = None
    ) -> Dict:
        momentum = self.calculate_narrative_momentum(narrative, previous_narratives or [])
        return {**narrative, "momentum": momentum}
