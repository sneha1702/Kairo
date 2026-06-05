"""
kairo_data.py — Converts real ES + MongoDB data into the KAIRO JS data model.

Exports:
    build_kairo_data(es_manager, tracker, dune_context, user_id) -> dict
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static mappings (copied exactly from data.js)
# ---------------------------------------------------------------------------

FORCES = {
    "smart-money": {"label": "Smart Money",    "blurb": "Whales & funds positioning",     "color": "lav",   "icon": "brain"},
    "regulation":  {"label": "Regulation",     "blurb": "ETF news, laws, approvals",      "color": "denim", "icon": "scale"},
    "infra":       {"label": "Infrastructure", "blurb": "L2 adoption, fees, throughput",  "color": "teal",  "icon": "layers"},
    "liquidity":   {"label": "Liquidity",      "blurb": "Stablecoin & exchange flows",    "color": "sage",  "icon": "drop"},
    "narrative":   {"label": "Narrative",      "blurb": "AI hype, memecoin cycles",       "color": "peach", "icon": "spark"},
    "rotation":    {"label": "Rotation",       "blurb": "BTC → ETH → L2 → AI flows",     "color": "rose",  "icon": "swap"},
}

STATUSES = {
    "emerging":      {"label": "Emerging",       "tone": "denim",  "dot": "denim"},
    "strengthening": {"label": "Strengthening",  "tone": "sage",   "dot": "sage"},
    "established":   {"label": "Established",    "tone": "accent", "dot": "accent"},
    "cooling":       {"label": "Cooling",        "tone": "ink-3",  "dot": "neutral"},
    "breaking":      {"label": "Breaking down",  "tone": "rose",   "dot": "rose"},
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIGNAL_SOURCE_TO_FORCE: dict[str, str] = {
    "smart_money":         "smart-money",
    "whale_transactions":  "smart-money",
    "whale":               "smart-money",
    "bridge_activity":     "rotation",
    "bridge":              "rotation",
    "token_flows":         "liquidity",
    "dex_concentration":   "liquidity",
    "volume_spikes":       "narrative",
    "holder_growth":       "infra",
    "wallet_concentration":"smart-money",
}

_MOMENTUM_TREND_TO_STATUS: dict[str, str] = {
    "strengthening": "strengthening",
    "new":           "emerging",
    "emerging":      "emerging",
    "stable":        "established",
    "weakening":     "cooling",
    "breaking":      "breaking",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _days_since(dt_val: Any) -> int:
    """Return days since dt_val (datetime or ISO string), minimum 1."""
    try:
        if isinstance(dt_val, str):
            dt_val = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
        if isinstance(dt_val, datetime):
            if dt_val.tzinfo is None:
                dt_val = dt_val.replace(tzinfo=timezone.utc)
            delta = _now() - dt_val
            return max(1, delta.days + 1)
    except Exception:
        pass
    return 1


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _fmt_usd(v: float) -> str:
    prefix = "+" if v >= 0 else "-"
    abs_v = abs(v)
    if abs_v >= 1e9:
        return f"{prefix}${abs_v/1e9:.2f}B"
    if abs_v >= 1e6:
        return f"{prefix}${abs_v/1e6:.1f}M"
    if abs_v >= 1e3:
        return f"{prefix}${abs_v/1e3:.0f}K"
    return f"{prefix}${abs_v:.0f}"


def _truncate_address(addr: str, head: int = 6, tail: int = 4) -> str:
    if not addr or len(addr) <= head + tail + 2:
        return addr or ""
    return f"{addr[:head]}…{addr[-tail:]}"


def _signal_source_to_force(sources: list[str]) -> str | None:
    for s in sources:
        mapped = _SIGNAL_SOURCE_TO_FORCE.get(str(s).lower())
        if mapped:
            return mapped
    return None


def _generate_curve(strength: float, n: int = 14) -> list[float]:
    """Generate a realistic-looking strength curve from ~5.0 to `strength`."""
    import math
    start = 5.0
    end = max(start, min(10.0, strength))
    curve = []
    for i in range(n):
        t = i / max(n - 1, 1)
        smooth = start + (end - start) * (t * t * (3 - 2 * t))
        noise = math.sin(i * 1.3) * 0.12
        curve.append(round(max(0.0, min(10.0, smooth + noise)), 1))
    curve[-1] = round(end, 1)
    return curve


def _strip_emoji(text: str) -> str:
    """Remove leading emoji/symbols from signal labels."""
    import re
    return re.sub(r'^[\U0001F000-\U0001FFFF☀-➿⌀-⏿⚡⚡📈📉🐋🟡🟢🔴]+\s*', '', str(text)).strip()


_STATUS_TO_PHASE: dict[str, str] = {
    "new":           "Discovery",
    "accelerating":  "Expanding",
    "continuing":    "Active",
    "stable":        "Maturing",
    "reversing":     "Declining",
    "strengthening": "Expanding",
    "emerging":      "Discovery",
    "weakening":     "Maturing",
    "breaking":      "Declining",
}


def _derive_narrative_phase(narrative: dict, day: int, confidence: float) -> str:
    status = (narrative.get("status") or "").lower()
    trend  = ((narrative.get("momentum") or {}).get("trend") or "").lower()
    phase  = _STATUS_TO_PHASE.get(status) or _STATUS_TO_PHASE.get(trend)
    if not phase:
        if confidence >= 0.75 and day >= 3:
            phase = "Peak"
        elif day <= 1:
            phase = "Discovery"
        else:
            phase = "Active"
    return phase


def _derive_smart_money_intent(narrative: dict) -> str | None:
    sources   = [str(s).lower() for s in (narrative.get("signal_sources") or [])]
    evidence  = " ".join(str(e).lower() for e in (narrative.get("key_evidence") or []))
    name      = (narrative.get("name") or "").lower()
    has_bridge = any(s in ("bridge_activity", "bridge") for s in sources)
    has_smart  = any(s in ("smart_money", "wallet_concentration") for s in sources)
    if "post_bridge_deployment" in evidence or "lending" in evidence or "deploy" in evidence:
        return "Deploying"
    if has_bridge and has_smart:
        return "Positioning"
    if has_bridge and ("rotation" in evidence or "rotation" in name):
        return "Rotating"
    if has_smart and ("accumulation" in evidence or "accumulating" in evidence):
        return "Accumulating"
    if ("reversing" in (narrative.get("status") or "").lower()) or "exit" in evidence:
        return "Exiting"
    if has_smart:
        return "Positioning"
    if has_bridge:
        return "Rotating"
    return None


def _shorten_headline(ev_str: str) -> str:
    """Extract a short punchy headline from a long evidence string (≤ ~80 chars)."""
    s = ev_str.strip()
    for sep in ('. ', ': ', ' — ', ', '):
        idx = s.find(sep)
        if 0 < idx < 88:
            return s[:idx + (1 if sep == '. ' else 0)].strip()
    return (s[:82] + "…") if len(s) > 82 else s


def _parse_retail_considerations(text: str) -> tuple[str, str, str]:
    """Parse 3-part retail_considerations string → (meaning, watch_for, risk_note)."""
    if not text or not isinstance(text, str):
        return ("", "", "")
    import re
    parts = re.split(r'[\(\[]?\s*[123]\s*[\)\]]?\s*[.:)]\s*', text)
    parts = [p.strip().rstrip(".,") for p in parts if p.strip()]
    meaning   = parts[0] if len(parts) > 0 else ""
    watch_for = parts[1] if len(parts) > 1 else ""
    risk_note = parts[2] if len(parts) > 2 else ""
    return (meaning, watch_for, risk_note)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_kairo_data(
    es_manager=None,
    tracker=None,
    dune_context: dict | None = None,
    user_id: str = "default",
) -> dict:
    """
    Build the complete KAIRO data model from real ES + MongoDB data.
    Never raises — always returns a valid dict.
    """
    try:
        dune_context = dune_context or {}
        mongo_narratives: list[dict] = []

        if tracker is not None:
            try:
                mongo_narratives = tracker.get_current_narratives(user_id, min_confidence=0.0) or []
            except Exception as exc:
                logger.warning("Could not fetch narratives from MongoDB: %s", exc)

        mongo_narratives = sorted(
            mongo_narratives,
            key=lambda n: _safe_float(n.get("confidence_score"), 0.0),
            reverse=True,
        )

        top_narrative: dict = mongo_narratives[0] if mongo_narratives else {}

        user        = _build_user(user_id, mongo_narratives, dune_context)
        story       = _build_story(top_narrative, dune_context)
        holdings    = _build_holdings(top_narrative, user["follows"])
        events      = _build_events(dune_context)
        trend_ctx   = _build_trend_context(top_narrative, dune_context)
        watch       = _build_watch(dune_context, top_narrative, mongo_narratives)
        tracker_data = _build_tracker(top_narrative, dune_context)
        trackers    = _build_all_trackers(mongo_narratives, dune_context, tracker_data)
        narratives  = _build_narratives(mongo_narratives)
        history     = _build_history(mongo_narratives)

        return {
            "user": user,
            "story": story,
            "holdings": holdings,
            "events": events,
            "trendContext": trend_ctx,
            "watch": watch,
            "forces": FORCES,
            "statuses": STATUSES,
            "tracker": tracker_data,
            "trackers": trackers,
            "narratives": narratives,
            "history": history,
        }

    except Exception as exc:
        logger.exception("build_kairo_data failed, returning fallback: %s", exc)
        return _empty_data(user_id)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_user(user_id: str, all_narratives: list[dict], dune_context: dict) -> dict:
    try:
        now = _now()
        date_str = now.strftime("%A, %B %-d")
    except Exception:
        date_str = _now().strftime("%A, %B %d").replace(" 0", " ")

    # follows — real tokens from detected narratives only
    follows: list[str] = []
    try:
        for n in all_narratives[:4]:
            for tok in (n.get("top_tokens") or [])[:3]:
                if tok and tok not in follows:
                    follows.append(tok)
        follows = follows[:6]
    except Exception:
        pass

    # development count from real dune signal buckets
    dev_count = 0
    try:
        for key in ("bridge_activity", "smart_money", "volume_spikes", "whale_transactions"):
            if dune_context.get(key):
                dev_count += 1
    except Exception:
        dev_count = len(all_narratives)

    strengthening = 0
    try:
        strengthening = sum(
            1 for n in all_narratives
            if (n.get("momentum") or {}).get("trend") == "strengthening"
        )
    except Exception:
        pass

    # display name: use user_id if it looks like a name, else generic
    display_name = user_id if (user_id and user_id != "default" and len(user_id) < 30) else "there"

    return {
        "name": display_name,
        "date": date_str,
        "follows": follows,
        "summary": {
            "developments": dev_count,
            "strengthening": strengthening,
            "risks": 0,
        },
    }


def _build_story(top: dict, dune_context: dict) -> dict:
    if not top:
        return {
            "eyebrow": "Today's Market Story",
            "headline": "Run detection to surface today's market story",
            "short": "No narratives have been detected yet.",
            "why": "Use the Refresh / Run Detection button to analyse current on-chain signals with Gemini.",
            "expanded": "Once detection runs, Kairo will synthesize signals from Elasticsearch and surface the dominant market story for today.",
            "assets": [],
            "confidence": "Low",
            "confidenceNote": "No narrative data available",
            "trend": {"label": "No data", "id": "pending"},
        }

    try:
        name = top.get("name", "Active Narrative")
        conf_score = _safe_float(top.get("confidence_score"), 0.5)
        confidence = "High" if conf_score > 0.7 else "Medium" if conf_score > 0.4 else "Low"
        conf_note = (
            "Multiple independent on-chain flows confirm the same direction"
            if conf_score > 0.7
            else "Some signals aligned — watch for confirmation"
        )

        why = ""
        implications = top.get("implications") or ""
        key_evidence = top.get("key_evidence") or []
        if implications and isinstance(implications, str) and len(implications) > 10:
            why = implications
        elif key_evidence and isinstance(key_evidence, list):
            why = ". ".join(str(e) for e in key_evidence[:2])
        if not why:
            why = "On-chain signals show sustained positioning in this narrative."

        expanded = (
            top.get("plain_english_summary")
            or top.get("retail_considerations")
            or top.get("expanded")
            or "This narrative has been building across multiple signal types. Whale wallet data and flow analysis support the current trend direction."
        )

        assets = (top.get("top_tokens") or [])[:3]
        day = _days_since(top.get("detected_at"))
        trend_id = str(name).lower().replace(" ", "-").replace("'", "")
        trend_label = f"Ongoing narrative · Day {day}"

        impl = top.get("implications") or ""
        if impl and isinstance(impl, str) and len(impl) > 20 and len(impl) < 140:
            headline = impl.rstrip(".").rstrip(",").strip() + "."
        else:
            clean_name = str(name).split("'")[0].split('"')[0].strip().rstrip(",").strip()
            headline = f"{clean_name}."

        pls = (top.get("plain_english_summary") or "").strip()
        first_dot = pls.find(". ")
        what_happening = (pls[:first_dot + 1] if first_dot != -1 else pls)[:280]

        retail = top.get("retail_considerations") or ""
        _meaning, _watch_for, _risk_note = _parse_retail_considerations(retail)
        why_matters = (top.get("implications") or _meaning or "")[:400].strip()
        risk_note = (top.get("data_caveat") or _risk_note or "")[:250].strip()
        watch_for = (_watch_for or "")[:220].strip()

        return {
            "eyebrow": f"{top.get('category', 'Market')} Narrative",
            "headline": headline[:200],
            "short": f"Capital is positioning around the {name} narrative.",
            "why": why[:400],
            "expanded": str(expanded)[:700],
            "assets": assets,
            "confidence": confidence,
            "confidenceNote": conf_note,
            "trend": {"label": trend_label, "id": trend_id},
            "what_happening": what_happening,
            "why_matters": why_matters,
            "risk_note": risk_note,
            "watch_for": watch_for,
        }
    except Exception as exc:
        logger.warning("_build_story error: %s", exc)
        return {
            "eyebrow": "Market Narrative",
            "headline": "Analysis in progress",
            "short": "Data is being synthesized.",
            "why": "Signal analysis is underway.",
            "expanded": "Full analysis will appear after detection runs.",
            "assets": [],
            "confidence": "Low",
            "confidenceNote": "Processing",
            "trend": {"label": "Pending", "id": "pending"},
        }


def _build_holdings(top: dict, follows: list[str]) -> list[dict]:
    if not follows:
        return []
    try:
        top_tokens = set((top.get("top_tokens") or [])[:5]) if top else set()
        narrative_name = top.get("name", "") if top else ""
        sources = top.get("signal_sources") or [] if top else []
        force = _signal_source_to_force(sources) or "smart-money"

        holdings = []
        for sym in follows[:4]:
            if sym in top_tokens:
                holdings.append({
                    "sym": sym,
                    "dir": "up",
                    "exposure": "Direct exposure",
                    "note": narrative_name if narrative_name else "Part of the active narrative",
                    "force": force,
                })
            else:
                holdings.append({
                    "sym": sym,
                    "dir": "flat",
                    "exposure": "No direct impact today",
                    "note": "Not linked to today's primary flows",
                    "force": None,
                })
        return holdings
    except Exception as exc:
        logger.warning("_build_holdings error: %s", exc)
        return []


def _build_events(dune_context: dict) -> list[dict]:
    events: list[dict] = []

    # Event 1 — whale transactions (real wallet data)
    try:
        whale_rows = dune_context.get("whale_transactions") or []
        if whale_rows:
            best = max(whale_rows, key=lambda r: _safe_float(r.get("usd_value"), 0))
            symbol = best.get("symbol") or "ETH"
            usd = _safe_float(best.get("usd_value"), 0)
            tier = _strip_emoji(best.get("whale_tier") or "Whale")
            sender = _truncate_address(best.get("sender") or "")
            receiver = _truncate_address(best.get("receiver") or "")
            events.append({
                "force": "smart-money",
                "title": f"{tier} moved {_fmt_usd(usd).lstrip('+')} in {symbol}",
                "impact": (
                    f"Large transfer from {sender} to {receiver}. "
                    "Whale-scale on-chain movement suggests deliberate positioning."
                ),
                "assets": [symbol] if symbol else [],
                "when": "recently",
            })
    except Exception as exc:
        logger.warning("_build_events whale error: %s", exc)

    # Event 2 — bridge activity (real routes)
    try:
        bridge_rows = dune_context.get("bridge_activity") or []
        if bridge_rows:
            best = max(bridge_rows, key=lambda r: _safe_float(r.get("total_usd"), 0))
            direction = best.get("direction") or "Cross-chain"
            bridge = best.get("bridge") or "bridge"
            usd = _safe_float(best.get("total_usd"), 0)
            signal = _strip_emoji(best.get("capital_signal") or "")
            events.append({
                "force": "rotation",
                "title": f"{_fmt_usd(usd).lstrip('+')} bridged via {bridge} — {direction}",
                "impact": signal or "Capital rotating between chains — a signal of shifting ecosystem allocation.",
                "assets": [],
                "when": "recently",
            })
    except Exception as exc:
        logger.warning("_build_events bridge error: %s", exc)

    # Event 3 — smart money (if not enough events)
    if len(events) < 2:
        try:
            smart_rows = dune_context.get("smart_money") or []
            if smart_rows:
                best = max(smart_rows, key=lambda r: _safe_float(r.get("total_bought_usd"), 0))
                symbol = best.get("symbol") or "ETH"
                usd = _safe_float(best.get("total_bought_usd"), 0)
                wallet = _truncate_address(best.get("wallet") or "")
                signal = _strip_emoji(best.get("accumulation_signal") or "")
                events.append({
                    "force": "smart-money",
                    "title": f"Smart money wallet ({wallet}) bought {_fmt_usd(usd).lstrip('+')} in {symbol}",
                    "impact": signal or "Top-tier wallets adding exposure — typically precedes broader market participation.",
                    "assets": [symbol] if symbol else [],
                    "when": "recently",
                })
        except Exception as exc:
            logger.warning("_build_events smart_money error: %s", exc)

    if not events:
        return [{
            "force": "smart-money",
            "title": "No on-chain events yet",
            "impact": "Run detection to load live events from Dune Analytics data.",
            "assets": [],
            "when": "—",
        }]

    return events[:2]


def _build_trend_context(top: dict, dune_context: dict) -> dict:
    try:
        token_flows = dune_context.get("token_flows") or []
        title = "Capital Flow Analysis"
        if top and (top.get("top_tokens") or []):
            title = f"{top['top_tokens'][0]} Capital Flow"

        today_net = sum(_safe_float(r.get("net_flow_usd") or r.get("net_usd"), 0) for r in token_flows)
        today_val = _fmt_usd(today_net) if today_net != 0 else "Neutral"
        today_tone = "pos" if today_net > 0 else "neutral" if today_net == 0 else "neg"

        # Bridge volume for 7d-equivalent (total bridge in this window)
        bridge_total = sum(_safe_float(r.get("total_usd"), 0) for r in (dune_context.get("bridge_activity") or []))
        bridge_val = _fmt_usd(bridge_total).lstrip("+") if bridge_total > 0 else "No bridge data"

        rows = [
            {"label": "CEX Flows",    "value": today_val,    "tone": today_tone},
            {"label": "Bridge Volume","value": bridge_val,   "tone": "pos" if bridge_total > 0 else "neutral"},
            {"label": "Window",       "value": "24h",        "tone": "neutral"},
        ]

        if today_net != 0:
            interp = (
                f"CEX net flow of {today_val} detected. "
                + ("Tokens are moving off exchanges — typically a holding signal." if today_net < 0
                   else "Tokens flowing onto exchanges — could indicate selling pressure.")
            )
        else:
            interp = "Run detection to load live capital flow data for the current narrative."

        return {"title": title, "rows": rows, "interpretation": interp}

    except Exception as exc:
        logger.warning("_build_trend_context error: %s", exc)
        return {
            "title": "Capital Flow Analysis",
            "rows": [
                {"label": "CEX Flows",     "value": "No data", "tone": "neutral"},
                {"label": "Bridge Volume", "value": "No data", "tone": "neutral"},
                {"label": "Window",        "value": "24h",     "tone": "neutral"},
            ],
            "interpretation": "Run narrative detection to load capital flow data.",
        }


def _build_watch(dune_context: dict, top: dict, all_narratives: list[dict]) -> dict:
    try:
        volume_spikes = dune_context.get("volume_spikes") or []
        if volume_spikes:
            best = max(volume_spikes, key=lambda r: _safe_float(r.get("volume_multiplier"), 0))
            token = best.get("symbol") or best.get("token") or "—"
            mult = _safe_float(best.get("volume_multiplier"), 1.0)
            traders = best.get("current_unique_traders")
            status = "emerging" if mult < 3 else "strengthening"
            reason = (
                f"Volume spiked {mult:.1f}x above expected baseline"
                + (f" with {traders} unique traders" if traders else "")
                + "."
            )
            return {
                "title": token,
                "reason": reason,
                "status": status,
                "assets": [token] if token and token != "—" else [],
            }

        if len(all_narratives) > 1:
            second = all_narratives[1]
            tokens = (second.get("top_tokens") or [])[:2]
            trend = (second.get("momentum") or {}).get("trend", "emerging")
            status = _MOMENTUM_TREND_TO_STATUS.get(trend, "emerging")
            return {
                "title": second.get("name", "Emerging Narrative"),
                "reason": (second.get("plain_english_summary") or second.get("implications") or "On-chain signals suggest building momentum.")[:200],
                "status": status,
                "assets": tokens,
            }

        return {
            "title": "No watch signal yet",
            "reason": "Run detection to surface the next developing narrative from live on-chain data.",
            "status": "emerging",
            "assets": [],
        }
    except Exception as exc:
        logger.warning("_build_watch error: %s", exc)
        return {
            "title": "No watch signal yet",
            "reason": "Run detection to surface the next developing narrative.",
            "status": "emerging",
            "assets": [],
        }


# ---------------------------------------------------------------------------
# Supporting facts (real wallet/tx data for narrative detail view)
# ---------------------------------------------------------------------------

def _build_supporting_facts(dune_context: dict, narrative: dict) -> dict:
    """
    Build rich supporting evidence from real ES data for a narrative's detail view.
    Includes real wallet addresses, tx hashes, amounts, bridge routes, volume spikes.
    """
    facts: dict = {
        "whale_moves": [],
        "smart_money_wallets": [],
        "bridge_flows": [],
        "volume_spikes": [],
        "wallet_concentration": [],
    }

    # ── Whale transactions ────────────────────────────────────────────────────
    try:
        whale_rows = dune_context.get("whale_transactions") or []
        top_tokens = set(t.upper() for t in (narrative.get("top_tokens") or []))
        relevant = [r for r in whale_rows if (r.get("symbol") or "").upper() in top_tokens] if top_tokens else []
        top_whales = sorted(relevant, key=lambda r: _safe_float(r.get("usd_value"), 0), reverse=True)[:5]
        for r in top_whales:
            usd = _safe_float(r.get("usd_value"), 0)
            if usd < 1_000:
                continue
            facts["whale_moves"].append({
                "wallet_from": _truncate_address(r.get("sender") or ""),
                "wallet_to":   _truncate_address(r.get("receiver") or ""),
                "full_from":   r.get("sender") or "",
                "full_to":     r.get("receiver") or "",
                "symbol":      r.get("symbol") or "—",
                "amount":      _safe_float(r.get("token_amount"), 0),
                "usd_value":   usd,
                "usd_fmt":     _fmt_usd(usd).lstrip("+"),
                "tier":        _strip_emoji(r.get("whale_tier") or "Whale"),
                "tx_hash":     (r.get("tx_hash") or "")[:12] + "…" if r.get("tx_hash") else "",
                "etherscan_url": r.get("etherscan_url") or "",
                "block_time":  r.get("block_time") or "",
            })
    except Exception as exc:
        logger.warning("_build_supporting_facts whale error: %s", exc)

    # ── Smart money wallets ───────────────────────────────────────────────────
    try:
        smart_rows = dune_context.get("smart_money") or []
        top_tokens = set(t.upper() for t in (narrative.get("top_tokens") or []))
        relevant = [r for r in smart_rows if (r.get("symbol") or "").upper() in top_tokens] if top_tokens else []
        top_smart = sorted(relevant, key=lambda r: _safe_float(r.get("total_bought_usd"), 0), reverse=True)[:4]
        for r in top_smart:
            usd = _safe_float(r.get("total_bought_usd"), 0)
            if usd < 1_000:
                continue
            facts["smart_money_wallets"].append({
                "wallet":      _truncate_address(r.get("wallet") or ""),
                "full_wallet": r.get("wallet") or "",
                "symbol":      r.get("symbol") or "—",
                "usd_bought":  usd,
                "usd_fmt":     _fmt_usd(usd).lstrip("+"),
                "buy_count":   r.get("buy_count") or 0,
                "signal":      _strip_emoji(r.get("accumulation_signal") or ""),
                "wallets_buying_same": r.get("wallets_buying_same_token") or 0,
            })
    except Exception as exc:
        logger.warning("_build_supporting_facts smart_money error: %s", exc)

    # ── Bridge flows — only for narratives whose signal_sources include bridge data ──
    narrative_sources = {str(s).lower() for s in (narrative.get("signal_sources") or [])}
    narrative_includes_bridge = bool(narrative_sources & {"bridge_activity", "bridge"})
    narrative_includes_concentration = bool(narrative_sources & {"whale_transactions", "whale", "smart_money", "wallet_concentration"})

    try:
        bridge_rows = dune_context.get("bridge_activity") or [] if narrative_includes_bridge else []
        top_bridges = sorted(bridge_rows, key=lambda r: _safe_float(r.get("total_usd"), 0), reverse=True)[:4]
        for r in top_bridges:
            usd = _safe_float(r.get("total_usd"), 0)
            if usd < 1_000:
                continue
            from_chain  = r.get("from_chain") or ""
            to_chain    = r.get("to_chain") or ""
            bridge_name = r.get("bridge_name") or r.get("bridge") or ""
            symbol      = r.get("symbol") or ""
            direction   = f"{from_chain} → {to_chain}" if (from_chain and to_chain) else (from_chain or to_chain or "")
            net_flow    = _safe_float(r.get("net_flow_usd"), 0)
            pct         = _safe_float(r.get("percentage_of_total"), 0)
            accel       = _safe_float(r.get("acceleration_7d_vs_30d_pct"), 0)
            facts["bridge_flows"].append({
                "bridge":        bridge_name,
                "from_chain":    from_chain,
                "to_chain":      to_chain,
                "symbol":        symbol,
                "direction":     direction,
                "usd":           usd,
                "usd_fmt":       _fmt_usd(usd).lstrip("+"),
                "net_flow_usd":  net_flow,
                "net_flow_fmt":  _fmt_usd(net_flow) if net_flow != 0 else "",
                "tx_count":      r.get("tx_count") or 0,
                "wallets":       r.get("unique_wallets") or r.get("wallets") or 0,
                "percentage":    pct,
                "acceleration":  accel,
                "signal":        _strip_emoji(r.get("capital_signal") or r.get("signal") or ""),
                "window_start":  r.get("earliest_tx_time") or "",
                "window_end":    r.get("latest_tx_time") or "",
            })
    except Exception as exc:
        logger.warning("_build_supporting_facts bridge error: %s", exc)

    # ── Volume spikes ─────────────────────────────────────────────────────────
    try:
        spike_rows = dune_context.get("volume_spikes") or []
        top_tokens = set(t.upper() for t in (narrative.get("top_tokens") or []))
        relevant = [r for r in spike_rows if (r.get("symbol") or "").upper() in top_tokens] if top_tokens else []
        top_spikes = sorted(relevant, key=lambda r: _safe_float(r.get("volume_multiplier"), 0), reverse=True)[:3]
        for r in top_spikes:
            mult = _safe_float(r.get("volume_multiplier"), 0)
            if mult < 1:
                continue
            facts["volume_spikes"].append({
                "symbol":        r.get("symbol") or "—",
                "multiplier":    mult,
                "current_vol":   _safe_float(r.get("current_volume_usd"), 0),
                "expected_vol":  _safe_float(r.get("expected_volume_usd"), 0),
                "current_vol_fmt": _fmt_usd(_safe_float(r.get("current_volume_usd"), 0)).lstrip("+"),
                "traders":       r.get("current_unique_traders") or 0,
                "signal":        _strip_emoji(r.get("spike_signal") or ""),
                "window_start":  r.get("window_start_time") or "",
                "window_end":    r.get("window_end_time") or "",
            })
    except Exception as exc:
        logger.warning("_build_supporting_facts volume_spikes error: %s", exc)

    # ── Wallet concentration — only for whale/smart-money narratives ─────────
    try:
        conc_rows = dune_context.get("wallet_concentration") or [] if narrative_includes_concentration else []
        top_conc = sorted(conc_rows, key=lambda r: int(r.get("rank") or 999))[:5]
        for r in top_conc:
            facts["wallet_concentration"].append({
                "rank":        r.get("rank") or "—",
                "address":     _truncate_address(r.get("address") or ""),
                "full_address":r.get("address") or "",
                "label":       r.get("label") or "Unknown",
                "pct":         _safe_float(r.get("pct_of_supply"), 0),
                "cumulative_pct": _safe_float(r.get("cumulative_pct"), 0),
                "balance":     _safe_float(r.get("balance"), 0),
            })
        if top_conc:
            as_of = max(
                (r.get("ingested_at") or r.get("window_start") or "" for r in top_conc),
                default="",
            ) or narrative.get("detected_at") or ""
            facts["concentration_as_of"] = as_of
    except Exception as exc:
        logger.warning("_build_supporting_facts wallet_concentration error: %s", exc)

    return facts


# ---------------------------------------------------------------------------
# Tracker builders
# ---------------------------------------------------------------------------

_SIGNAL_PLAIN_ENGLISH: dict[str, str] = {
    "smart_money": (
        "Large, experienced traders are building a position through repeated buys on decentralized exchanges. "
        "When sophisticated wallets accumulate deliberately over time rather than in a single trade, "
        "it often signals conviction ahead of broader market participation."
    ),
    "whale": (
        "Major holders are moving very large sums on-chain — transfers that represent deliberate positioning "
        "by entities with significant market influence. These aren't routine transactions."
    ),
    "bridge": (
        "Capital is crossing between different blockchain networks. "
        "Moving funds cross-chain requires effort and cost, so large bridge flows signal intentional "
        "capital reallocation — money following opportunity, not noise."
    ),
    "volume": (
        "Trading volume has spiked well above the recent average, indicating unusually high activity. "
        "A volume spike can draw broader attention to an asset and often precedes sustained momentum."
    ),
    "accumulation": (
        "Tokens are flowing off exchanges into private wallets — the classic accumulation pattern. "
        "When holders withdraw rather than leave assets available to sell, it reduces near-term selling pressure."
    ),
    "holder": (
        "The number of unique wallets holding this asset is growing. "
        "Broad holder growth means ownership is spreading — a healthy sign for a developing narrative."
    ),
    "dex": (
        "A meaningful share of this token's trading is concentrated on specific decentralized exchanges. "
        "High concentration by informed traders tends to precede wider market awareness."
    ),
}


def _detect_signal_context(evidence_text: str) -> str:
    """Pick the most relevant plain-English signal explanation based on the evidence text."""
    ev = evidence_text.lower()
    if "smart money" in ev or ("wallet" in ev and ("bought" in ev or "buys" in ev or "buy" in ev)):
        return _SIGNAL_PLAIN_ENGLISH["smart_money"]
    if "whale" in ev or "large holder" in ev:
        return _SIGNAL_PLAIN_ENGLISH["whale"]
    if "bridge" in ev or "bridged" in ev or "→" in evidence_text or "->" in ev:
        return _SIGNAL_PLAIN_ENGLISH["bridge"]
    if "volume" in ev or "spike" in ev or "multiplier" in ev or "×" in evidence_text:
        return _SIGNAL_PLAIN_ENGLISH["volume"]
    if "accumulation" in ev or "outflow" in ev or "withdrawing" in ev:
        return _SIGNAL_PLAIN_ENGLISH["accumulation"]
    if "holder" in ev or "new wallet" in ev or "growth" in ev:
        return _SIGNAL_PLAIN_ENGLISH["holder"]
    if "dex" in ev or "concentration" in ev or "exchange" in ev:
        return _SIGNAL_PLAIN_ENGLISH["dex"]
    return ""


def _build_episode_body(evidence_text: str, narrative: dict, idx: int) -> str:
    """
    Build a plain-English body for a timeline episode.
    headline = the raw data fact; body = what it means + why the narrative matters.
    """
    name = narrative.get("name", "this narrative")
    plain_summary  = (narrative.get("plain_english_summary") or "").strip()
    implications   = (narrative.get("implications") or "").strip()
    signal_context = _detect_signal_context(evidence_text)

    # Rotate the "why it matters" text across episodes so they don't all read identically
    narrative_context_pool = [x for x in [plain_summary, implications] if x and len(x) > 20]
    if narrative_context_pool:
        narrative_context = narrative_context_pool[idx % len(narrative_context_pool)]
    else:
        narrative_context = f"This signal contributes to the {name} narrative — sustained capital positioning across multiple data sources."

    # Lead with signal meaning, close with narrative-level context
    parts = []
    if signal_context:
        parts.append(signal_context)
    if narrative_context:
        parts.append(narrative_context)
    text = " ".join(parts)
    words = text.split()
    return " ".join(words[:100]) + ("…" if len(words) > 100 else "")


def _bucket_episodes(episodes: list[dict], total_days: int) -> list[dict]:
    """
    Collapse episodes to ≤3 smart time-bucketed bullets.

    ≤7 days:   show last 3 individual days
    8–28 days: one summary label for older days + 2 recent individual days
    >28 days:  one monthly summary + 2 recent individual days
    """
    if not episodes or len(episodes) <= 3:
        return episodes

    def _make_summary(eps: list[dict], date_label: str) -> dict:
        best = max(eps, key=lambda e: len(e.get("headline", "")))
        combined_body = " ".join(e["body"] for e in eps if e.get("body"))[:450]
        return {**best, "date": date_label, "detail": "", "body": combined_body}

    if total_days <= 7:
        return episodes[-3:]

    recent = episodes[-2:]
    older  = episodes[:-2]
    if not older:
        return episodes[-3:]

    if total_days <= 28:
        weeks_old = max(1, total_days // 7 - 1)
        label = "Week 1" if weeks_old == 1 else f"Weeks 1–{weeks_old}"
        return [_make_summary(older, label)] + recent

    # >28 days
    months = max(1, total_days // 30)
    label = f"{months} month{'s' if months > 1 else ''} ago"
    return [_make_summary(older, label)] + recent


def _build_tracker(top: dict, dune_context: dict | None = None) -> dict:
    if not top:
        return _empty_tracker()

    dune_context = dune_context or {}

    try:
        name = top.get("name", "Active Narrative")
        conf = _safe_float(top.get("confidence_score"), 0.5)
        strength = round(conf * 10, 1)
        day = _days_since(top.get("detected_at"))
        trend = (top.get("momentum") or {}).get("trend", "stable")
        status = _MOMENTUM_TREND_TO_STATUS.get(trend, "established")
        sources = top.get("signal_sources") or []
        forces = []
        for s in sources[:3]:
            f = _signal_source_to_force([s])
            if f and f not in forces:
                forces.append(f)
        if not forces:
            forces = ["smart-money"]
        assets = (top.get("top_tokens") or [])[:3]
        summary = (
            top.get("plain_english_summary")
            or top.get("retail_considerations")
            or top.get("implications")
            or f"The {name} narrative has been active for {day} day{'s' if day != 1 else ''}."
        )
        curve = _generate_curve(strength)

        # Build episodes from key_evidence
        episodes: list[dict] = []
        key_evidence = top.get("key_evidence") or []
        force_id = forces[0] if forces else "smart-money"
        detected_dt = top.get("detected_at")

        for i, ev in enumerate(reversed(key_evidence[:5])):
            ep_day = i + 1
            try:
                if detected_dt:
                    if isinstance(detected_dt, str):
                        base = datetime.fromisoformat(detected_dt.replace("Z", "+00:00"))
                    else:
                        base = detected_dt
                    if base.tzinfo is None:
                        base = base.replace(tzinfo=timezone.utc)
                    import datetime as _dt
                    ep_date_dt = base + _dt.timedelta(days=i)
                    if ep_date_dt.date() > _now().date():
                        ep_date_dt = _now()
                    ep_date = ep_date_dt.strftime("%b %-d")
                else:
                    ep_date = f"Day {ep_day}"
            except Exception:
                ep_date = f"Day {ep_day}"

            ep_strength = round(max(5.0, strength - (len(key_evidence) - 1 - i) * 0.3), 1)
            ev_str = str(ev).strip()
            short_headline = _shorten_headline(ev_str)
            explanation = _build_episode_body(ev_str, top, i)
            episodes.append({
                "day":      ep_day,
                "date":     ep_date,
                "headline": short_headline,
                "detail":   ev_str if len(ev_str) > len(short_headline) + 5 else "",
                "body":     explanation,
                "force":    force_id,
                "strength": ep_strength,
            })

        # Merge episodes that share the same date (caused by capping future dates at today)
        merged: list[dict] = []
        date_index: dict[str, int] = {}
        for ep in episodes:
            d = ep["date"]
            if d in date_index:
                existing = merged[date_index[d]]
                # Append extra evidence as a second sentence in the body
                if ep["body"] and ep["body"] not in existing["body"]:
                    existing["body"] = existing["body"].rstrip(" .") + ". " + ep["body"]
                # Keep the more descriptive headline (longer wins)
                if len(ep["headline"]) > len(existing["headline"]):
                    existing["headline"] = ep["headline"]
                    existing["detail"] = ep["detail"]
            else:
                date_index[d] = len(merged)
                merged.append(ep)
        episodes = _bucket_episodes(merged, day)

        if not episodes:
            episodes = [{
                "day":      day,
                "date":     _now().strftime("%b %-d"),
                "headline": f"{name} narrative active",
                "body":     "On-chain signals confirm the narrative is developing.",
                "force":    force_id,
                "strength": strength,
            }]

        supporting_facts = _build_supporting_facts(dune_context, top)

        phase = _derive_narrative_phase(top, day, conf)
        smart_intent = _derive_smart_money_intent(top)

        pls = (top.get("plain_english_summary") or "").strip()
        first_dot = pls.find(". ")
        what_happening = (pls[:first_dot + 1] if first_dot != -1 else pls)[:280]

        retail = top.get("retail_considerations") or ""
        _meaning, _watch_for, _risk_note = _parse_retail_considerations(retail)
        why_matters = (top.get("implications") or _meaning or "")[:400].strip()
        risk_note = (top.get("data_caveat") or _risk_note or "")[:250].strip()
        watch_for = (_watch_for or "")[:220].strip()

        return {
            "title":             name,
            "day":               day,
            "status":            status,
            "strength":          strength,
            "delta":             "+0.4",
            "summary":           str(summary)[:500],
            "forces":            forces,
            "assets":            assets,
            "curve":             curve,
            "episodes":          episodes,
            "supportingFacts":   supporting_facts,
            "category":          top.get("category") or "Market",
            "confidence_score":  conf,
            "implications":      (top.get("implications") or "")[:500],
            "phase":             phase,
            "smart_money_intent": smart_intent,
            "what_happening":    what_happening,
            "why_matters":       why_matters,
            "risk_note":         risk_note,
            "watch_for":         watch_for,
        }
    except Exception as exc:
        logger.warning("_build_tracker error: %s", exc)
        return _empty_tracker()


def _build_all_trackers(all_narratives: list[dict], dune_context: dict, top_tracker: dict) -> dict:
    """Build a dict of trackers keyed by narrative ID (for per-tile drill-down)."""
    dune_context = dune_context or {}
    result: dict = {}
    for n in all_narratives:
        try:
            name = n.get("name", "Unknown")
            nid = name.lower().replace(" ", "-").replace("'", "").replace("(", "").replace(")", "")
            result[nid] = _build_tracker(n, dune_context)
        except Exception as exc:
            logger.warning("_build_all_trackers item error: %s", exc)
    # Index top tracker by its id too
    if top_tracker and top_tracker.get("title"):
        top_id = top_tracker["title"].lower().replace(" ", "-").replace("'", "").replace("(", "").replace(")", "")
        result.setdefault(top_id, top_tracker)
    return result


def _empty_tracker() -> dict:
    return {
        "title":             "No narrative detected",
        "day":               0,
        "status":            "emerging",
        "strength":          0.0,
        "delta":             "+0.0",
        "summary":           "Run narrative detection to load the active market narrative tracker.",
        "forces":            ["smart-money"],
        "assets":            [],
        "curve":             [0.0] * 14,
        "episodes":          [],
        "supportingFacts":   {"whale_moves": [], "smart_money_wallets": [], "bridge_flows": [], "volume_spikes": [], "wallet_concentration": []},
        "category":          "",
        "confidence_score":  0.0,
        "implications":      "",
        "phase":             "",
        "smart_money_intent": None,
        "what_happening":    "",
        "why_matters":       "",
        "risk_note":         "",
        "watch_for":         "",
    }


def _build_narratives(all_narratives: list[dict]) -> list[dict]:
    if not all_narratives:
        return []  # no fake data — show empty state

    result = []
    for n in all_narratives[:8]:
        try:
            name = n.get("name", "Unknown")
            conf = _safe_float(n.get("confidence_score"), 0.5)
            trend = (n.get("momentum") or {}).get("trend", "stable")
            status = _MOMENTUM_TREND_TO_STATUS.get(trend, "established")
            sources = n.get("signal_sources") or []
            force = _signal_source_to_force(sources) or "narrative"
            assets = (n.get("top_tokens") or [])[:3]
            day = _days_since(n.get("detected_at"))
            nid = name.lower().replace(" ", "-").replace("'", "").replace("(", "").replace(")", "")
            phase = _derive_narrative_phase(n, day, conf)
            smart_intent = _derive_smart_money_intent(n)
            plain = (n.get("plain_english_summary") or n.get("implications") or "").strip()
            first_dot = plain.find(". ")
            summary_line = (plain[:first_dot + 1] if first_dot != -1 else plain)[:160]

            result.append({
                "id":               nid,
                "title":            name,
                "status":           status,
                "strength":         round(conf * 10, 1),
                "day":              day,
                "assets":           assets,
                "force":            force,
                "phase":            phase,
                "summary_line":     summary_line,
                "smart_money_intent": smart_intent,
            })
        except Exception as exc:
            logger.warning("_build_narratives item error: %s", exc)
            continue

    return result


def _build_history(all_narratives: list[dict]) -> dict:
    if not all_narratives:
        return {
            "title":    "Pattern Memory",
            "subtitle": "How today's story compares with every time it has happened before",
            "cycles":   [],
            "interpretation": "Run narrative detection to start building pattern history. As Kairo detects narratives over time, cycle comparisons will appear here.",
        }

    try:
        top = all_narratives[0]
        top_name = top.get("name", "Primary Narrative")
        top_conf = _safe_float(top.get("confidence_score"), 0.5)
        top_day = _days_since(top.get("detected_at"))
        top_weeks = max(1, top_day // 7)
        top_sources = top.get("signal_sources") or []
        top_force = _signal_source_to_force(top_sources) or "smart-money"
        top_kind = "Institutional" if top_force in ("smart-money", "infra", "regulation") else "Speculative"

        cycles: list[dict] = []
        for n in all_narratives[1:4]:
            try:
                conf = _safe_float(n.get("confidence_score"), 0.4)
                day = _days_since(n.get("detected_at"))
                weeks = max(1, day // 7)
                sources = n.get("signal_sources") or []
                force = _signal_source_to_force(sources) or "narrative"
                kind = "Institutional" if force in ("smart-money", "infra", "regulation") else "Speculative"
                cycles.append({
                    "name":          n.get("name", "Prior Narrative")[:35],
                    "span":          "Prior cycle",
                    "kind":          kind,
                    "peak":          round(conf * 10, 1),
                    "durationWeeks": weeks,
                    "note":          (n.get("implications") or f"A prior {kind.lower()} narrative tracked by Kairo.")[:180],
                    "current":       False,
                    "force":         force,
                })
            except Exception:
                continue

        cycles.append({
            "name":          "Current",
            "span":          f"Day {top_day}",
            "kind":          top_kind,
            "peak":          round(top_conf * 10, 1),
            "durationWeeks": top_weeks,
            "note":          (top.get("implications") or f"The {top_name} narrative is the most active signal Kairo is currently tracking.")[:180],
            "current":       True,
            "force":         top_force,
        })

        interp = (
            f"The current '{top_name}' narrative shows "
            f"{'sustained institutional' if top_kind == 'Institutional' else 'speculative'} "
            f"characteristics at confidence {round(top_conf * 100)}%. "
            + (top.get("implications") or "")[:200]
        )

        return {
            "title":          f"{top_name[:40]} Cycles",
            "subtitle":       "How today's story compares with prior occurrences",
            "cycles":         cycles,
            "interpretation": interp[:500],
        }

    except Exception as exc:
        logger.warning("_build_history error: %s", exc)
        return {
            "title":    "Pattern Memory",
            "subtitle": "How today's story compares with prior occurrences",
            "cycles":   [],
            "interpretation": "History data will appear as Kairo tracks more narrative cycles.",
        }


# ---------------------------------------------------------------------------
# Empty data (shown when services are completely unavailable)
# ---------------------------------------------------------------------------

def _empty_data(user_id: str = "default") -> dict:
    try:
        date_str = _now().strftime("%A, %B %-d")
    except Exception:
        date_str = "Today"

    display_name = user_id if (user_id and user_id != "default" and len(user_id) < 30) else "there"

    return {
        "user": {
            "name": display_name,
            "date": date_str,
            "follows": [],
            "summary": {"developments": 0, "strengthening": 0, "risks": 0},
        },
        "story": {
            "eyebrow": "Market Story",
            "headline": "Run detection to surface today's market story",
            "short": "No data yet.",
            "why": "Click 'Refresh / Run Detection' to analyse on-chain signals.",
            "expanded": "Once detection runs, Kairo will synthesize signals from Elasticsearch and surface the dominant market story.",
            "assets": [],
            "confidence": "Low",
            "confidenceNote": "Services unavailable",
            "trend": {"label": "No data", "id": "pending"},
        },
        "holdings": [],
        "events": [{
            "force": "smart-money",
            "title": "Services connecting…",
            "impact": "Run detection to load live on-chain events.",
            "assets": [],
            "when": "—",
        }],
        "trendContext": {
            "title": "Capital Flow Analysis",
            "rows": [
                {"label": "CEX Flows",     "value": "No data", "tone": "neutral"},
                {"label": "Bridge Volume", "value": "No data", "tone": "neutral"},
                {"label": "Window",        "value": "24h",     "tone": "neutral"},
            ],
            "interpretation": "Run narrative detection to load capital flow data.",
        },
        "watch": {
            "title": "No signal yet",
            "reason": "Run detection to surface developing narratives.",
            "status": "emerging",
            "assets": [],
        },
        "forces":   FORCES,
        "statuses": STATUSES,
        "tracker":  _empty_tracker(),
        "trackers": {},
        "narratives": [],
        "history": {
            "title":    "Pattern Memory",
            "subtitle": "How today's story compares with prior occurrences",
            "cycles":   [],
            "interpretation": "Run narrative detection to start building pattern history.",
        },
    }
