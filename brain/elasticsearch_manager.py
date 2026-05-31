"""
Elasticsearch Manager: Handles whale transaction data indexing and retrieval.
"""

from elasticsearch import Elasticsearch
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json


class ElasticsearchManager:
    def __init__(self, es_url: str, username: str, password: str, api_key_id: str):
        """Initialize Elasticsearch connection."""
        self.logger = logging.getLogger(__name__)
        self.logger.info("Connecting to Elasticsearch at %s", es_url)

        self.es = Elasticsearch(
            es_url,
 #           basic_auth=(username, password)
            api_key=(api_key_id)
        )

        try:
            ok = self.es.ping()
            self.logger.info("Elasticsearch ping status: %s", ok)
        except Exception as e:
            self.logger.exception("Error pinging Elasticsearch: %s", e)
        self.whale_transactions_index = "whale_transactions"
        self._ensure_whale_index()
    
    def _ensure_whale_index(self):
        """Create whale_transactions index if it doesn't exist."""
        try:
            exists = self.es.indices.exists(index=self.whale_transactions_index)
        except Exception:
            exists = False

        if not exists:
            self.logger.info("Creating index %s", self.whale_transactions_index)
            self.es.indices.create(
                index=self.whale_transactions_index,
                body={
                    "mappings": {
                        "properties": {
                            "wallet": {"type": "keyword"},
                            "token": {"type": "keyword"},
                            "category": {"type": "keyword"},
                            "action": {"type": "keyword"},
                            "amount_usd": {"type": "float"},
                            "amount_tokens": {"type": "float"},
                            "timestamp": {"type": "date"},
                            "chain": {"type": "keyword"},
                            "tx_hash": {"type": "keyword"},
                            "price_impact": {"type": "float"},
                            "slippage": {"type": "float"}
                        }
                    },
                }
            )
        else:
            self.logger.info("Index %s already exists", self.whale_transactions_index)
    
    def get_client(self) -> Elasticsearch:
        """Return the Elasticsearch client."""
        return self.es
    
    def ingest_transactions(self, transactions: List[Dict[str, Any]]):
        """Ingest whale transactions into Elasticsearch."""
        for i, doc in enumerate(transactions):
            # Ensure timestamp is ISO format
            if isinstance(doc.get('timestamp'), str):
                doc['timestamp'] = doc['timestamp']
            else:
                doc['timestamp'] = datetime.now().isoformat()
            
            self.es.index(
                index=self.whale_transactions_index,
                id=f"{doc.get('tx_hash', doc.get('wallet', ''))}-{i}",
                body=doc
            )
    
    def get_recent_transactions(self, hours: int = 24, 
                               min_usd: float = 0) -> List[Dict[str, Any]]:
        """Get recent whale transactions."""
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        response = self.es.search(
            index=self.whale_transactions_index,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"range": {"timestamp": {"gte": since}}},
                            {"range": {"amount_usd": {"gte": min_usd}}}
                        ]
                    }
                },
                "sort": [{"timestamp": {"order": "desc"}}],
                "size": 1000
            }
        )
        
        return [hit["_source"] for hit in response["hits"]["hits"]]
    
    def get_category_activity(self, hours: int = 24) -> Dict[str, Any]:
        """Get whale activity aggregated by category."""
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        response = self.es.search(
            index=self.whale_transactions_index,
            body={
                "query": {
                    "range": {"timestamp": {"gte": since}}
                },
                "aggs": {
                    "by_category": {
                        "terms": {"field": "category", "size": 50},
                        "aggs": {
                            "total_volume": {"sum": {"field": "amount_usd"}},
                            "tx_count": {"value_count": {"field": "wallet"}},
                            "buy_volume": {
                                "sum": {
                                    "field": "amount_usd",
                                    "filter": {"term": {"action": "BUY"}}
                                }
                            },
                            "top_tokens": {
                                "terms": {"field": "token", "size": 10}
                            }
                        }
                    }
                }
            }
        )
        
        result = {}
        for bucket in response["aggregations"]["by_category"]["buckets"]:
            result[bucket["key"]] = {
                "volume": bucket["total_volume"]["value"],
                "tx_count": bucket["tx_count"]["value"],
                "buy_volume": bucket.get("buy_volume", {}).get("value", 0),
                "top_tokens": [t["key"] for t in bucket["top_tokens"]["buckets"]]
            }
        
        return result
    
    def get_token_activity(self, token: str, hours: int = 24) -> Dict[str, Any]:
        """Get whale activity for a specific token."""
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        response = self.es.search(
            index=self.whale_transactions_index,
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"token": token}},
                            {"range": {"timestamp": {"gte": since}}}
                        ]
                    }
                },
                "aggs": {
                    "buy_sell_split": {
                        "terms": {"field": "action"},
                        "aggs": {
                            "volume": {"sum": {"field": "amount_usd"}}
                        }
                    },
                    "whale_count": {"cardinality": {"field": "wallet"}},
                    "total_volume": {"sum": {"field": "amount_usd"}}
                }
            }
        )
        
        result = {
            "token": token,
            "total_volume": response["aggregations"]["total_volume"]["value"],
            "whale_count": response["aggregations"]["whale_count"]["value"],
            "buy_sell_data": {}
        }
        
        for bucket in response["aggregations"]["buy_sell_split"]["buckets"]:
            result["buy_sell_data"][bucket["key"]] = bucket["volume"]["value"]
        
        return result
    
    def get_top_active_whales(self, hours: int = 24, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top whale wallets by transaction count."""
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        response = self.es.search(
            index=self.whale_transactions_index,
            body={
                "query": {
                    "range": {"timestamp": {"gte": since}}
                },
                "aggs": {
                    "top_whales": {
                        "terms": {"field": "wallet", "size": limit},
                        "aggs": {
                            "volume": {"sum": {"field": "amount_usd"}},
                            "tx_count": {"value_count": {"field": "token"}},
                            "recent_action": {
                                "top_hits": {
                                    "size": 1,
                                    "sort": [{"timestamp": {"order": "desc"}}]
                                }
                            }
                        }
                    }
                }
            }
        )
        
        whales = []
        for bucket in response["aggregations"]["top_whales"]["buckets"]:
            whales.append({
                "wallet": bucket["key"],
                "volume": bucket["volume"]["value"],
                "tx_count": bucket["tx_count"]["value"],
                "avg_tx_size": bucket["volume"]["value"] / max(bucket["tx_count"]["value"], 1)
            })
        
        return whales
    
    def get_dune_signal_context(self, hours: int = 24) -> Dict[str, Any]:
        """Query the 6 aggregate dune_* indices and return structured context for NarrativeEngine."""
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        range_filter = {"range": {"ingested_at": {"gte": since}}}

        def _search(index: str, size: int = 50) -> List[Dict]:
            try:
                resp = self.es.search(
                    index=index,
                    body={"query": range_filter, "sort": [{"ingested_at": {"order": "desc"}}], "size": size},
                )
                return [h["_source"] for h in resp["hits"]["hits"]]
            except Exception as exc:
                self.logger.warning("Could not query %s: %s", index, exc)
                return []

        return {
            "whale_transactions":  _search("dune_whale_transactions"),
            "smart_money":         _search("dune_smart_money"),
            "token_flows":         _search("dune_token_flows"),
            "bridge_activity":     _search("dune_bridge_activity"),
            "wallet_concentration": _search("dune_wallet_concentration", size=50),
            "volume_spikes":       _search("dune_volume_spikes"),
            "holder_growth":       _search("dune_holder_growth"),
            "dex_concentration":   _search("dune_dex_concentration"),
        }

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
                    self.logger.debug("signal_trend fetch %s: %s", index, exc)
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

        return buckets

    def get_emerging_tokens(self, hours: int = 24, min_transactions: int = 3) -> List[Dict[str, Any]]:
        """Find tokens with sudden whale activity increase."""
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        response = self.es.search(
            index=self.whale_transactions_index,
            body={
                "query": {
                    "range": {"timestamp": {"gte": since}}
                },
                "aggs": {
                    "by_token": {
                        "terms": {"field": "token", "size": 1000},
                        "aggs": {
                            "volume": {"sum": {"field": "amount_usd"}},
                            "whale_count": {"cardinality": {"field": "wallet"}},
                            "tx_count": {"value_count": {"field": "timestamp"}}
                        }
                    }
                }
            }
        )
        
        tokens = []
        for bucket in response["aggregations"]["by_token"]["buckets"]:
            if bucket["tx_count"]["value"] >= min_transactions:
                tokens.append({
                    "token": bucket["key"],
                    "volume": bucket["volume"]["value"],
                    "whale_count": bucket["whale_count"]["value"],
                    "tx_count": bucket["tx_count"]["value"]
                })
        
        return sorted(tokens, key=lambda x: x["volume"], reverse=True)
