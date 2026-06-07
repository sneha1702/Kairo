"""
Shared types and abstract base class for all ingestion pipeline providers.

Each provider (Dune, Flipside, …) implements BaseIngestionPipeline so that
higher-level code (pipeline_runner, backfill) is provider-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Signal / index mappings shared by every provider ──────────────────────────

QUERY_TO_INDEX: dict[str, str] = {
    "whale_transaction_filter":    "dune_whale_transactions",
    "smart_money_accumulation":    "dune_smart_money",
    "token_inflow_outflow":        "dune_token_flows",
    "bridge_activity":             "dune_bridge_activity",
    "wallet_concentration":        "dune_wallet_concentration",
    "volume_spike_detection":      "dune_volume_spikes",
    "new_holder_growth":           "dune_holder_growth",
    "dex_trading_concentration":   "dune_dex_concentration",
    "post_bridge_deployment":      "dune_post_bridge_deployment",
    "stablecoin_liquidity_flow":   "dune_stablecoin_flows",
    "ecosystem_sector_rotation":   "dune_sector_rotation",
    "protocol_inflow_leaderboard": "dune_protocol_inflows",
}

QUERY_TO_SIGNAL: dict[str, str] = {
    "whale_transaction_filter":    "WHALE_FLOW",
    "smart_money_accumulation":    "SMART_MONEY",
    "token_inflow_outflow":        "TOKEN_FLOW",
    "bridge_activity":             "BRIDGE",
    "wallet_concentration":        "CONCENTRATION",
    "volume_spike_detection":      "VOLUME_SPIKE",
    "new_holder_growth":           "HOLDER_GROWTH",
    "dex_trading_concentration":   "DEX_LIQUIDITY",
    "post_bridge_deployment":      "CAPITAL_DEPLOYMENT",
    "stablecoin_liquidity_flow":   "STABLECOIN_FLOW",
    "ecosystem_sector_rotation":   "SECTOR_ROTATION",
    "protocol_inflow_leaderboard": "PROTOCOL_INFLOW",
}

CADENCE_GROUPS: dict[int, list[str]] = {
    6:  [
        "whale_transaction_filter", "smart_money_accumulation",
        "volume_spike_detection",   "dex_trading_concentration",
        "post_bridge_deployment",   "stablecoin_liquidity_flow",
        "ecosystem_sector_rotation","protocol_inflow_leaderboard",
    ],
    24: [
        "token_inflow_outflow", "bridge_activity",
        "new_holder_growth",    "wallet_concentration",
    ],
}


# ── Shared data classes ────────────────────────────────────────────────────────

@dataclass
class QueryConfig:
    query_name: str
    sql_path: Path
    params: dict[str, Any]
    cadence_hours: int
    signal_category: str
    target_index: str


@dataclass
class IngestionResult:
    query_name: str
    success: bool = False
    rows_fetched: int = 0
    docs_indexed: int = 0
    docs_failed: int = 0
    failed_docs: list[dict] = field(default_factory=list)
    error: Exception | None = None
    duration_seconds: float = 0.0
    provider: str = "unknown"


# ── Abstract base ──────────────────────────────────────────────────────────────

class BaseIngestionPipeline(ABC):
    """Common interface for all ingestion providers."""

    provider_name: str = "unknown"

    @abstractmethod
    def run_all(
        self,
        query_names: list[str] | None = None,
        dry_run: bool = False,
        end_time: str | None = None,
        time_window_hours: int | None = None,
    ) -> dict[str, IngestionResult]:
        """Run all (or a subset of) queries and return results keyed by query name."""

    @abstractmethod
    def run_one(self, qc: QueryConfig, dry_run: bool = False) -> IngestionResult:
        """Run a single query described by *qc* and return its result."""
