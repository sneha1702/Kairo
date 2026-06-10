"""
Elasticsearch Manager: Handles whale transaction data indexing and retrieval.
"""

from elasticsearch import Elasticsearch
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any


class ElasticsearchManager:
    def __init__(self, es_url: str, username: str, password: str, api_key_id: str):
        """Initialize Elasticsearch connection."""
        self.logger = logging.getLogger(__name__)
        self._available = False
        self.logger.info("Connecting to Elasticsearch at %s", es_url)

        self.es = Elasticsearch(
            es_url,
            api_key=(api_key_id),
            request_timeout=10,
        )

        try:
            ok = self.es.ping()
            self._available = bool(ok)
            self.logger.info("Elasticsearch ping status: %s", ok)
        except Exception as e:
            self.logger.warning("Elasticsearch unavailable (%s: %s) — ES features disabled.", type(e).__name__, e)
    
    def get_client(self) -> Elasticsearch:
        """Return the Elasticsearch client."""
        return self.es
    
    
    def get_dune_signal_context(self, hours: int = 168) -> Dict[str, Any]:
        """Query the 6 aggregate dune_* indices and return structured context for NarrativeEngine."""
        if not self._available:
            self.logger.warning("[ES] Skipping get_dune_signal_context — Elasticsearch not available.")
            return {}
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        range_filter = {"range": {"ingested_at": {"gte": since}}}
        self.logger.info("[ES] Fetching Dune signal context — lookback=%dh, since=%s", hours, since)

        def _search(index: str, size: int = 50) -> List[Dict]:
            try:
                resp = self.es.search(
                    index=index,
                    body={"query": range_filter, "sort": [{"ingested_at": {"order": "desc"}}], "size": size},
                )
                docs = [h["_source"] for h in resp["hits"]["hits"]]
                self.logger.info("[ES] %-32s → %d docs", index, len(docs))
                return docs
            except Exception as exc:
                self.logger.warning("[ES] Could not query %s: %s", index, exc)
                return []

        context = {
            "whale_transactions":   _search("dune_whale_transactions"),
            "smart_money":          _search("dune_smart_money"),
            "token_flows":          _search("dune_token_flows"),
            "bridge_activity":      _search("dune_bridge_activity"),
            "wallet_concentration": _search("dune_wallet_concentration", size=50),
            "volume_spikes":        _search("dune_volume_spikes"),
            "holder_growth":        _search("dune_holder_growth"),
            "dex_concentration":    _search("dune_dex_concentration"),
        }
        total = sum(len(v) for v in context.values())
        self.logger.info("[ES] Signal context ready — %d total docs across 8 indices", total)
        return context

    def get_signal_trend(self, hours_per_bucket: int = 24, num_buckets: int = 3) -> List[Dict[str, Any]]:
        """
        Returns per-signal aggregate metrics across `num_buckets` consecutive time windows.
        Oldest bucket first so Gemini can read left-to-right acceleration.
        E.g. num_buckets=3, hours_per_bucket=24 → T-72h..T-48h, T-48h..T-24h, T-24h..now
        """
        now = datetime.now()
        buckets: List[Dict[str, Any]] = []

        def _num(v: Any) -> float:
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        def _top_symbols(docs: List[Dict], *fields: str) -> List[str]:
            seen: Dict[str, float] = {}
            for d in docs:
                sym = d.get("symbol") or d.get("token") or d.get("token_address") or ""
                if not sym:
                    continue
                amt = max((_num(d.get(f)) for f in fields), default=0.0)
                seen[sym] = seen.get(sym, 0.0) + amt
            return [s for s, _ in sorted(seen.items(), key=lambda x: -x[1])][:5]

        self.logger.info("[ES] Building signal trend — %d buckets × %dh each", num_buckets, hours_per_bucket)

        for i in range(num_buckets - 1, -1, -1):
            bucket_end   = now - timedelta(hours=i * hours_per_bucket)
            bucket_start = bucket_end - timedelta(hours=hours_per_bucket)
            label = f"T-{(i + 1) * hours_per_bucket}h..T-{i * hours_per_bucket}h" if i > 0 else f"T-{hours_per_bucket}h..now"

            def _fetch(index: str, size: int = 100) -> List[Dict]:
                try:
                    resp = self.es.search(
                        index=index,
                        body={
                            "query": {"range": {"ingested_at": {
                                "gte": bucket_start.isoformat(),
                                "lt":  bucket_end.isoformat(),
                            }}},
                            "size": size,
                        },
                    )
                    return [h["_source"] for h in resp["hits"]["hits"]]
                except Exception as exc:
                    self.logger.warning("[ES] signal_trend fetch %s: %s", index, exc)
                    return []

            whales    = _fetch("dune_whale_transactions")
            sm        = _fetch("dune_smart_money")
            flows     = _fetch("dune_token_flows")
            bridges   = _fetch("dune_bridge_activity")
            spikes    = _fetch("dune_volume_spikes")

            buckets.append({
                "bucket":              label,
                "whale_tx_count":      len(whales),
                "whale_usd":           sum(_num(d.get("usd_value")) for d in whales),
                "whale_top_symbols":   _top_symbols(whales, "usd_value"),
                "smart_money_usd":     sum(_num(d.get("total_bought_usd")) for d in sm),
                "smart_money_wallets": len({d.get("wallet") for d in sm if d.get("wallet")}),
                "smart_money_top":     _top_symbols(sm, "total_bought_usd"),
                "net_flow_usd":        sum(_num(d.get("net_flow_usd")) for d in flows),
                "bridge_usd":          sum(_num(d.get("total_usd")) for d in bridges),
                "bridge_tx_count":     sum(int(_num(d.get("tx_count", 0))) for d in bridges),
                "volume_spike_max":    max((_num(d.get("volume_multiplier")) for d in spikes), default=0.0),
                "volume_spike_count":  len(spikes),
                "spike_top_symbols":   _top_symbols(spikes, "volume_multiplier"),
            })

        self.logger.info("[ES] Signal trend ready — %d buckets", len(buckets))
        return buckets

