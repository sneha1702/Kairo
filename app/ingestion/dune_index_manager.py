"""
DuneIndexManager: idempotent creation of all 8 dune_* Elasticsearch indices.
"""

import logging
from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

# Common metadata fields added to every document by DuneIngestionPipeline.
# time_bucket / category / signals / signal_count are returned by every SQL query.
_METADATA_PROPERTIES: dict = {
    "ingested_at":        {"type": "date"},
    "query_name":         {"type": "keyword"},
    "signal_category":    {"type": "keyword"},
    "time_window_hours":  {"type": "integer"},
    "window_start":       {"type": "date"},
    "params_snapshot":    {"type": "object", "dynamic": False},
    # Common signal schema fields present in every query output
    "time_bucket":        {"type": "date"},
    "category":           {"type": "keyword"},
    "signals":            {"type": "keyword"},   # ES handles arrays of keyword natively
    "signal_count":       {"type": "integer"},
}

_SETTINGS_DEFAULT: dict = {}   # serverless Elastic Cloud does not accept shard/replica settings

_INDEX_MAPPINGS: dict = {
    "dune_whale_transactions": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "block_time":      {"type": "date"},
            "symbol":          {"type": "keyword"},
            "sender":          {"type": "keyword"},
            "receiver":        {"type": "keyword"},
            "token_amount":    {"type": "double"},
            "usd_value":       {"type": "double"},
            "total_usd":       {"type": "double"},
            "whale_usd":       {"type": "double"},
            "smart_money_usd": {"type": "double"},
            "tx_hash":         {"type": "keyword"},
            "etherscan_url":   {"type": "keyword", "index": False},
        },
    },
    "dune_smart_money": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "symbol":                        {"type": "keyword"},
            "smart_money_usd":               {"type": "double"},
            "whale_usd":                     {"type": "double"},
            "net_flow_usd":                  {"type": "double"},
            "smart_money_concentration_pct": {"type": "double"},
            "wallet_count":                  {"type": "integer"},
            "total_smart_money_flow_usd":    {"type": "double"},
            "wallets_buying_same_token":     {"type": "integer"},
        },
    },
    "dune_token_flows": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "symbol":              {"type": "keyword"},
            "from_chain":          {"type": "keyword"},
            "to_chain":            {"type": "keyword"},
            "inflow_tokens":       {"type": "double"},
            "outflow_tokens":      {"type": "double"},
            "gross_inflow_usd":    {"type": "double"},
            "gross_outflow_usd":   {"type": "double"},
            "net_flow_usd":        {"type": "double"},
            "earliest_flow_time":  {"type": "date"},
            "latest_flow_time":    {"type": "date"},
        },
    },
    "dune_bridge_activity": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "symbol":                    {"type": "keyword"},
            "from_chain":                {"type": "keyword"},
            "to_chain":                  {"type": "keyword"},
            "bridge_name":               {"type": "keyword"},
            "gross_inflow_usd":          {"type": "double"},
            "gross_outflow_usd":         {"type": "double"},
            "bridge_usd":                {"type": "double"},
            "net_flow_usd":              {"type": "double"},
            "total_usd":                 {"type": "double"},
            "percentage_of_total":       {"type": "double"},
            "tx_count":                  {"type": "integer"},
            # Enriched by app layer from ES history; absent in fresh docs is fine
            "acceleration_7d_vs_30d_pct": {"type": "double"},
        },
    },
    "dune_wallet_concentration": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "symbol":                        {"type": "keyword"},
            "rank":                          {"type": "integer"},
            "address":                       {"type": "keyword"},
            "label":                         {"type": "keyword"},
            "address_type":                  {"type": "keyword"},
            "balance":                       {"type": "double"},
            "pct_of_supply":                 {"type": "double"},
            "cumulative_pct":                {"type": "double"},
            "whale_concentration_pct":       {"type": "double"},
            "smart_money_concentration_pct": {"type": "double"},
            "snapshot_time":                 {"type": "date"},
            "token_address":                 {"type": "keyword"},
        },
    },
    "dune_volume_spikes": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "symbol":                    {"type": "keyword"},
            "current_volume_usd":        {"type": "double"},
            "expected_volume_usd":       {"type": "double"},
            "volume_multiplier":         {"type": "double"},
            "current_trades":            {"type": "integer"},
            "expected_trades":           {"type": "double"},
            "current_unique_traders":    {"type": "integer"},
            "window_start_time":         {"type": "date"},
            "window_end_time":           {"type": "date"},
            # Enriched by app layer from ES history
            "acceleration_7d_vs_30d_pct": {"type": "double"},
        },
    },
    "dune_holder_growth": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "symbol":                  {"type": "keyword"},
            "new_wallets":             {"type": "integer"},
            "prior_new_wallets":       {"type": "integer"},
            "holder_growth_pct":       {"type": "double"},
            "total_holders_all_time":  {"type": "integer"},
            "first_time_users_pct":    {"type": "double"},
            "active_addresses":        {"type": "integer"},
            "window_start_time":       {"type": "date"},
            "window_end_time":         {"type": "date"},
            "token_address":           {"type": "keyword"},
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
            "whale_concentration_pct":  {"type": "double"},
            "volume_multiplier":        {"type": "double"},
            "earliest_trade_time":      {"type": "date"},
            "latest_trade_time":        {"type": "date"},
        },
    },
    "dune_post_bridge_deployment": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "symbol":              {"type": "keyword"},
            "chain":               {"type": "keyword"},
            "deployment_type":     {"type": "keyword"},
            "protocol":            {"type": "keyword"},
            "net_flow_usd":        {"type": "double"},
            "total_usd":           {"type": "double"},
            "percentage_of_total": {"type": "double"},
            "new_wallets":         {"type": "integer"},
            "tx_count":            {"type": "integer"},
        },
    },
    "dune_stablecoin_flows": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "symbol":          {"type": "keyword"},
            "mint_usd":        {"type": "double"},
            "burn_usd":        {"type": "double"},
            "net_flow_usd":    {"type": "double"},
            "total_usd":       {"type": "double"},
            "mint_growth_pct": {"type": "double"},
            "new_wallets":     {"type": "integer"},
        },
    },
    "dune_sector_rotation": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "symbol":              {"type": "keyword"},
            "gross_inflow_usd":    {"type": "double"},
            "gross_outflow_usd":   {"type": "double"},
            "net_flow_usd":        {"type": "double"},
            "total_usd":           {"type": "double"},
            "percentage_of_total": {"type": "double"},
            "trade_count":         {"type": "integer"},
            "unique_traders":      {"type": "integer"},
            "volume_multiplier":   {"type": "double"},
        },
    },
    "dune_protocol_inflows": {
        "settings": _SETTINGS_DEFAULT,
        "fields": {
            "symbol":            {"type": "keyword"},
            "deployment_type":   {"type": "keyword"},
            "net_flow_usd":      {"type": "double"},
            "total_usd":         {"type": "double"},
            "whale_usd":         {"type": "double"},
            "new_wallets":       {"type": "integer"},
            "volume_multiplier": {"type": "double"},
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
