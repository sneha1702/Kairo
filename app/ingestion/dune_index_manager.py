"""
DuneIndexManager: idempotent creation of all 8 dune_* Elasticsearch indices.
"""

import logging
from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

# Common metadata fields added to every document by DuneIngestionPipeline
_METADATA_PROPERTIES: dict = {
    "ingested_at":        {"type": "date"},
    "query_name":         {"type": "keyword"},
    "signal_category":    {"type": "keyword"},
    "time_window_hours":  {"type": "integer"},
    "window_start":       {"type": "date"},
    "params_snapshot":    {"type": "object", "dynamic": False},
}

_SETTINGS_DEFAULT: dict = {}   # serverless Elastic Cloud does not accept shard/replica settings

_INDEX_MAPPINGS: dict = {
    "dune_whale_transactions": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "block_time":     {"type": "date"},
            "symbol":         {"type": "keyword"},
            "sender":         {"type": "keyword"},
            "receiver":       {"type": "keyword"},
            "token_amount":   {"type": "double"},
            "usd_value":      {"type": "double"},
            "whale_tier":     {"type": "keyword"},
            "tx_hash":        {"type": "keyword"},
            "etherscan_url":  {"type": "keyword", "index": False},
        },
    },
    "dune_smart_money": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "wallet":                      {"type": "keyword"},
            "symbol":                      {"type": "keyword"},
            "buy_count":                   {"type": "integer"},
            "total_bought_usd":            {"type": "double"},
            "first_buy":                   {"type": "date"},
            "last_buy":                    {"type": "date"},
            "time_span_minutes":           {"type": "float"},
            "accumulation_signal":         {"type": "keyword"},
            "total_smart_money_flow_usd":  {"type": "double"},
            "wallets_buying_same_token":   {"type": "integer"},
        },
    },
    "dune_token_flows": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "token":               {"type": "keyword"},
            "inflow_tokens":       {"type": "double"},
            "outflow_tokens":      {"type": "double"},
            "inflow_usd":          {"type": "double"},
            "outflow_usd":         {"type": "double"},
            "net_flow_usd":        {"type": "double"},
            "earliest_flow_time":  {"type": "date"},
            "latest_flow_time":    {"type": "date"},
            "signal":              {"type": "keyword"},
        },
    },
    "dune_bridge_activity": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "direction":         {"type": "keyword"},
            "bridge":            {"type": "keyword"},
            "tx_count":          {"type": "integer"},
            "unique_wallets":    {"type": "integer"},
            "total_eth":         {"type": "double"},
            "total_usd":         {"type": "double"},
            "earliest_tx_time":  {"type": "date"},
            "latest_tx_time":    {"type": "date"},
            "capital_signal":    {"type": "keyword"},
        },
    },
    "dune_wallet_concentration": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "rank":           {"type": "integer"},
            "address":        {"type": "keyword"},
            "label":          {"type": "keyword"},
            "address_type":   {"type": "keyword"},
            "balance":        {"type": "double"},
            "pct_of_supply":  {"type": "double"},
            "cumulative_pct": {"type": "double"},
            "snapshot_time":  {"type": "date"},
            "token_address":  {"type": "keyword"},
        },
    },
    "dune_volume_spikes": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "symbol":                  {"type": "keyword"},
            "current_volume_usd":      {"type": "double"},
            "expected_volume_usd":     {"type": "double"},
            "volume_multiplier":       {"type": "double"},
            "current_trades":          {"type": "integer"},
            "expected_trades":         {"type": "double"},
            "current_unique_traders":  {"type": "integer"},
            "window_start_time":       {"type": "date"},
            "window_end_time":         {"type": "date"},
            "spike_signal":            {"type": "keyword"},
        },
    },
    "dune_holder_growth": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "view_type":                    {"type": "keyword"},
            "new_holders_current_window":   {"type": "integer"},
            "new_holders_prior_window":     {"type": "integer"},
            "growth_rate_pct":              {"type": "double"},
            "total_holders_all_time":       {"type": "integer"},
            "new_holders_pct_of_total":     {"type": "double"},
            "growth_signal":                {"type": "keyword"},
            "token_address":                {"type": "keyword"},
        },
    },
    "dune_dex_concentration": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "symbol":                   {"type": "keyword"},
            "dex":                      {"type": "keyword"},
            "pool_volume_usd":          {"type": "double"},
            "trade_count":              {"type": "integer"},
            "unique_traders":           {"type": "integer"},
            "avg_trade_usd":            {"type": "double"},
            "dex_share_pct":            {"type": "double"},
            "top10_wallets_share_pct":  {"type": "double"},
            "concentration_signal":     {"type": "keyword"},
        },
    },
}


class DuneIndexManager:
    def __init__(self, es_client: Elasticsearch):
        self.es = es_client

    def ensure_all_indices(self) -> None:
        for name in _INDEX_MAPPINGS:
            self.ensure_index(name)

    def ensure_index(self, name: str) -> None:
        try:
            exists = self.es.indices.exists(index=name)
        except Exception:
            exists = False

        spec = _INDEX_MAPPINGS[name]
        properties = {**_METADATA_PROPERTIES, **spec["fields"]}

        if exists:
            # Push any new fields added to the mapping definition without recreating the index.
            try:
                self.es.indices.put_mapping(index=name, body={"properties": properties})
                logger.debug("Mapping synced for %s", name)
            except Exception as exc:
                logger.warning("Could not sync mapping for %s: %s", name, exc)
            return

        body: dict = {"mappings": {"dynamic": "strict", "properties": properties}}
        if spec["settings"]:
            body["settings"] = spec["settings"]
        logger.info("Creating index %s", name)
        self.es.indices.create(index=name, body=body)
