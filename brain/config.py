"""
Configuration management for the Narrative Evolution Agent.
"""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Application configuration."""
    
    # Elasticsearch
    ES_URL: str = os.getenv("ES_URL", "https://my-elasticsearch-project-d9aecb.es.europe-west1.gcp.elastic.cloud:443")
    ES_USERNAME: str = os.getenv("ES_USERNAME", "elastic")
    ES_PASSWORD: str = os.getenv("ES_PASSWORD", "dNZBYMpC*u$!r7A")
    ES_API_KEY_ID: str = os.getenv("ES_API_KEY_ID", "aDJYbFg1NEJVNTE3RGRHZXZjUjk6WHk4QmkxcHl3VTN2WVZHd2QyaHlkQQ==")
    
    # Google Gemini
    GEMINI_KEY: str = os.getenv("GEMINI_KEY", "AIzaSyDf8uUKnKuGmrlYQeZRXQhxKw2uZxVvCpY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # Application Settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    # Narrative Settings
    MIN_NARRATIVE_CONFIDENCE: float = float(os.getenv("MIN_NARRATIVE_CONFIDENCE", "0.5"))
    MAX_NARRATIVES_PER_DETECTION: int = int(os.getenv("MAX_NARRATIVES_PER_DETECTION", "5"))
    NARRATIVE_HISTORY_DAYS: int = int(os.getenv("NARRATIVE_HISTORY_DAYS", "7"))
    
    # Index names — existing
    WHALE_TRANSACTIONS_INDEX: str = "whale_transactions"
    NARRATIVES_INDEX: str = "narratives"
    NARRATIVE_HISTORY_INDEX: str = "narrative_history"

    # Index names — Dune ingestion (one per query)
    DUNE_WHALE_TRANSACTIONS_INDEX: str = "dune_whale_transactions"
    DUNE_SMART_MONEY_INDEX: str = "dune_smart_money"
    DUNE_TOKEN_FLOWS_INDEX: str = "dune_token_flows"
    DUNE_BRIDGE_ACTIVITY_INDEX: str = "dune_bridge_activity"
    DUNE_WALLET_CONCENTRATION_INDEX: str = "dune_wallet_concentration"
    DUNE_VOLUME_SPIKES_INDEX: str = "dune_volume_spikes"
    DUNE_HOLDER_GROWTH_INDEX: str = "dune_holder_growth"
    DUNE_DEX_CONCENTRATION_INDEX: str = "dune_dex_concentration"

    # MongoDB
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb+srv://kairoDBAdmin:KvghCaQGqqyK2k7U@kairocluster.wwrd9ag.mongodb.net/")
    MONGO_DB: str = os.getenv("MONGO_DB", "kairo")

    # Dune pipeline settings
    QUERY_DIR: str = os.getenv("QUERY_DIR", "ingestion/query")
    DUNE_API_KEY: str = os.getenv("DUNE_API_KEY", "")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration."""
        required = ['ES_URL', 'ES_USERNAME', 'ES_PASSWORD', 'GEMINI_KEY']
        missing = [key for key in required if not getattr(cls, key)]
        
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")
        
        return True
    
    @classmethod
    def to_dict(cls) -> dict:
        """Get configuration as dictionary."""
        return {
            key: getattr(cls, key)
            for key in dir(cls)
            if not key.startswith('_') and key.isupper()
        }


class NarrativeConfig:
    """Narrative-specific configuration."""
    
    # Narrative detection prompt template
    DETECTION_PROMPT_TEMPLATE = """
You are an elite crypto narrative intelligence analyst. Analyze the whale activity below and identify emerging narratives.

CURRENT WHALE ACTIVITY:
{whale_activity}

**TASK**: Identify **maximum 3 emerging narratives** from this whale activity.

For EACH narrative, provide JSON response with these EXACT fields:
- name: Catchy narrative title (e.g., "AI Agent Accumulation", "Gaming Revival")
- category: Primary category
- strength: "High" | "Medium" | "Low" (based on volume & frequency)
- momentum: "Strengthening" | "Stable" | "Weakening"
- confidence_score: 0.0-1.0 (how confident this is an emerging narrative)
- key_evidence: Array of 2-3 key pieces of evidence
- implications: What this means for the market
- top_tokens: Array of top 3 tokens in this narrative
- retail_considerations: What retail investors should know

Return ONLY valid JSON array, no markdown, no explanation.
"""
    
    # Minimum whale activity thresholds
    MIN_WHALE_TX_VALUE_USD: float = 10_000
    MIN_WHALE_TRANSACTIONS: int = 2
    MIN_WHALE_CATEGORY_VOLUME: float = 50_000
    
    # Confidence calculation weights
    VOLUME_WEIGHT: float = 0.3
    FREQUENCY_WEIGHT: float = 0.3
    CONSENSUS_WEIGHT: float = 0.4
    
    # Momentum calculation
    MOMENTUM_LOOKBACK_DAYS: int = 7
    MOMENTUM_THRESHOLD_STRENGTHENING: float = 0.1  # 10% increase
    MOMENTUM_THRESHOLD_WEAKENING: float = -0.1     # 10% decrease


class StreamlitConfig:
    """Streamlit-specific configuration."""
    
    PAGE_TITLE: str = "Kairo Agent"
    PAGE_ICON: str = "🔮"
    LAYOUT: str = "wide"
    INITIAL_SIDEBAR_STATE: str = "expanded"
    
    # Dashboard refresh interval (seconds)
    REFRESH_INTERVAL: int = 60
    
    # Chart settings
    CHART_HEIGHT: int = 400
    CHART_WIDTH: str = '100%'


def get_config() -> Config:
    """Get the application configuration instance."""
    return Config()


def validate_config() -> bool:
    """Validate all configuration."""
    try:
        Config.validate()
        return True
    except ValueError as e:
        print(f"Configuration error: {e}")
        return False
