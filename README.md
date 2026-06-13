# 🔮 Narrative Evolution Agent

A sophisticated AI agent that detects emerging crypto narratives from whale wallet activity using Elasticsearch and Google's Gemini API. Tracks narrative strength, momentum, and evolution over time.

## 🎯 Features

- **Real-time Narrative Detection**: Analyzes whale activity patterns to identify emerging narratives
- **Gemini-Powered Inference**: Uses advanced LLM to infer narrative meaning from on-chain activity
- **Momentum Tracking**: Monitors if narratives are strengthening or weakening
- **Confidence Scoring**: Assigns confidence scores based on evidence volume and consistency
- **Time-Series Storage**: Maintains historical narrative data for trend analysis
- **User Tracking**: Track specific narratives and receive updates
- **Interactive Dashboard**: Streamlit UI for visualization and interaction

## 📋 System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Whale Activity                        │
│              (On-chain Transaction Data)                 │
└────────────────────┬────────────────────────────────────┘
                     │
         ┌───────────▼───────────┐
         │  Elasticsearch Manager │  Indexes & retrieves
         └───────────┬───────────┘  whale transactions
                     │
         ┌───────────▼───────────────┐
         │  Narrative Engine          │  Groups activity,
         │  (Gemini-powered)          │  infers narratives
         └───────────┬───────────────┘
                     │
         ┌───────────▼───────────────┐
         │  Narrative Tracker         │  Tracks & stores
         │  (Time-series ES index)    │  narrative evolution
         └───────────┬───────────────┘
                     │
         ┌───────────▼────────────────┐
         │   Streamlit Dashboard       │  User interface
         └─────────────────────────────┘
```

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.9+
- Elasticsearch instance (cloud or local)
- Google Gemini API key

### 2. Installation

```bash
# Clone the repository
cd KairoAgent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration

Create a `.streamlit/secrets.toml` file:

```toml
# Elasticsearch
ES_URL = "https://your-es-url:443"
ES_USERNAME = "elastic"
ES_PASSWORD = "your-password"

# Google Gemini
GEMINI_KEY = "your-gemini-api-key"
```

Or set environment variables:

```bash
export ES_URL="https://your-es-url:443"
export ES_USERNAME="elastic"
export ES_PASSWORD="your-password"
export GEMINI_KEY="your-gemini-api-key"
```

### 4. Data Ingestion

First, ingest sample whale transaction data:

```bash
python ingest.py
```

This reads `data/transactions.json` and indexes it into Elasticsearch.

### 5. Run the Application

```bash
streamlit run app.py
```

The app will be available at `http://localhost:8501`

## 📊 How It Works

### 1. Whale Activity Analysis

The system monitors whale wallet transactions grouped by token category:

```json
{
  "AI": {
    "total_volume_usd": 430000,
    "tx_count": 2,
    "tokens": ["FET", "AGIX"],
    "buy_volume": 430000,
    "sell_volume": 0,
    "buy_sell_ratio": inf
  }
}
```

### 2. Narrative Detection

Gemini analyzes activity patterns and generates narratives:

```json
{
  "name": "AI Agent Infrastructure Surge",
  "category": "AI",
  "strength": "High",
  "confidence_score": 0.85,
  "momentum": "Strengthening",
  "key_evidence": [
    "Two major whale accumulations (FET + AGIX)",
    "430k USD in buys with zero sells",
    "100% positive sentiment"
  ],
  "implications": "Whales believe AI agents are the next big trend",
  "top_tokens": ["FET", "AGIX", "RENDER"]
}
```

### 3. Momentum Tracking

Compares current narratives against historical data:

- **Strengthening**: Confidence and volume increasing
- **Stable**: No significant change
- **Weakening**: Confidence or volume decreasing
- **Emerging**: New narrative detected

### 4. Storage

Narratives stored in two Elasticsearch indices:

- **`narratives`**: Current active narratives
- **`narrative_history`**: Time-series data for trend analysis

## 📚 API Reference

### NarrativeEngine

```python
from narrative_engine import NarrativeEngine

engine = NarrativeEngine(gemini_api_key="...")

# Group whale activity by category
grouped = engine.group_whale_activity(transactions)

# Detect narratives
narratives = engine.detect_narratives(whale_activity)

# Calculate momentum
momentum = engine.calculate_narrative_momentum(current, historical)

# Enrich with metadata
enriched = engine.enrich_narrative(narrative, historical)
```

### NarrativeTracker

```python
from narrative_tracker import NarrativeTracker

tracker = NarrativeTracker(es_client)

# Save narratives
tracker.save_narratives(narratives, user_id="default")

# Get current narratives
current = tracker.get_current_narratives(user_id, min_confidence=0.5)

# Get tracked narratives
tracked = tracker.get_tracked_narratives(user_id)

# Track/untrack
tracker.track_narrative("AI Agent Boom", user_id)
tracker.untrack_narrative("AI Agent Boom", user_id)

# Get history
history = tracker.get_narrative_history("AI Agent Boom", days=7, user_id)

# Get stats
stats = tracker.get_narrative_stats(user_id)
```

### ElasticsearchManager

```python
from elasticsearch_manager import ElasticsearchManager

es = ElasticsearchManager(url, username, password)

# Get recent transactions
txs = es.get_recent_transactions(hours=24, min_usd=10000)

# Get category activity
activity = es.get_category_activity(hours=24)

# Get token activity
token_act = es.get_token_activity("FET", hours=24)

# Get top whales
whales = es.get_top_active_whales(hours=24, limit=10)

# Get emerging tokens
emerging = es.get_emerging_tokens(hours=24, min_transactions=3)
```

## 🎨 Streamlit Dashboard Tabs

### 🔍 Detect Narratives
- Analyze whale activity for the selected timeframe
- View detected narratives with confidence scores
- Track narratives you're interested in
- See detailed evidence and implications

### 📊 Narrative Dashboard
- View all detected narratives
- See statistics (total, tracked, strengthening)
- Monitor strengthening narratives
- Quick overview of narrative landscape

### ⭐ Tracked Narratives
- View narratives you're actively monitoring
- See 7-day confidence and momentum trends
- Untrack narratives when no longer interested

### 📈 Narrative History
- Deep dive into specific narrative evolution
- View confidence and momentum trends over time
- See maximum confidence reached
- Track historical performance

## 🔧 Configuration Options

### Sidebar Settings

- **User ID**: Segment narratives by user
- **Hours to Analyze**: How far back to look (1-168 hours)
- **Minimum Confidence**: Filter narratives by confidence threshold

## 📊 Data Flow

1. **Data Collection**: Whale transactions indexed into Elasticsearch
2. **Grouping**: Transactions grouped by category and token
3. **Analysis**: Gemini analyzes patterns to extract narratives
4. **Scoring**: Narratives scored by confidence and momentum
5. **Storage**: Saved to Elasticsearch indices
6. **Visualization**: Displayed in Streamlit dashboard

## 🎯 Example Workflow

1. **Morning**: Run narrative detection to see what whales are accumulating
2. **Track**: Choose narratives that align with your thesis
3. **Monitor**: Check tracked narratives dashboard daily
4. **Analyze**: Review 7-day history to see momentum
5. **Decide**: Use narrative strength to inform trading/investment decisions

## 🔐 Security Best Practices

- Store credentials in `.streamlit/secrets.toml` (Git ignored)
- Use environment variables for CI/CD pipelines
- Rotate Elasticsearch and Gemini API keys regularly
- Restrict Elasticsearch to VPC/IP whitelist in production

## 📖 Sample Data Format

`data/transactions.json`:

```json
[
  {
    "wallet": "0xA1",
    "token": "FET",
    "category": "AI",
    "action": "BUY",
    "amount_usd": 250000,
    "timestamp": "2026-05-25T10:00:00"
  },
  {
    "wallet": "0xB7",
    "token": "AGIX",
    "category": "AI",
    "action": "BUY",
    "amount_usd": 180000,
    "timestamp": "2026-05-25T10:05:00"
  }
]
```

## 🚀 Production Deployment

### Using Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["streamlit", "run", "app.py"]
```

### Using Streamlit Cloud

1. Push repo to GitHub
2. Go to share.streamlit.io
3. Deploy with secrets.toml configuration

## 🐛 Troubleshooting

### Elasticsearch Connection Failed
- Verify ES_URL is correct
- Check credentials (ES_USERNAME, ES_PASSWORD)
- Ensure IP is whitelisted (cloud instances)

### Gemini API Error
- Verify GEMINI_KEY is valid
- Check API quota and rate limits
- Ensure billing is enabled

### No Narratives Detected
- Ensure whale transaction data is ingested
- Check timeframe (hours_lookback)
- Lower min_confidence threshold
- Run ingest.py again: `python ingest.py`

## 📝 Advanced Usage

### Custom Prompt Engineering

Edit the prompt in `narrative_engine.py` `detect_narratives()` method:

```python
prompt = f"""
You are [CUSTOM ROLE]...
[CUSTOM INSTRUCTIONS]...
"""
```

### Custom Aggregations

Add custom Elasticsearch aggregations in `elasticsearch_manager.py`

### Webhook Integration

Add webhook notifications in `narrative_tracker.py`:

```python
def notify_on_track(narrative, user_id):
    # Send webhook, email, or Slack notification
    pass
```

## 📄 License

MIT License - See LICENSE file for details

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 💡 Future Enhancements

- [ ] Real-time WebSocket updates
- [ ] Cross-chain narrative analysis
- [ ] Sentiment analysis from social media
- [ ] Automated alerts and notifications
- [ ] Mobile app interface
- [ ] Advanced ML clustering
- [ ] Narrative correlation analysis
- [ ] Backtesting framework

## 📧 Support

For issues and questions:
- Open GitHub issues for bugs
- Discuss features in discussions
- Email: [your-email]

---

## Ingestion Architecture Principles

The ingestion subsystem is designed so that adding or replacing a data provider (Dune, DefiLlama, or anything future) requires zero changes to Elasticsearch mappings, MongoDB schemas, or the Gemini synthesis layer.

### Layer overview

```
┌──────────────────────────────────────────────────────────┐
│                    Data Sources                          │
│   Dune Analytics API          DefiLlama REST API         │
│   (SQL / Trino)               (pre-aggregated, no auth)  │
└───────────────┬───────────────────────┬──────────────────┘
                │                       │
    ┌───────────▼──────────┐ ┌──────────▼──────────────┐
    │  DuneIngestionPipeline│ │DefiLlamaIngestionPipeline│
    │  (dune_pipeline.py)   │ │(defillama_pipeline.py)   │
    └───────────┬──────────┘ └──────────┬───────────────┘
                │     raw rows           │     raw rows
                └──────────┬────────────┘
                           │
              ┌────────────▼────────────────┐
              │     signal_transformer.py    │
              │  1. Field mapping            │
              │  2. Schema enforcement       │
              │  3. Metadata envelope        │
              │  4. Deterministic _id        │
              └────────────┬────────────────┘
                           │  canonical docs
          ┌────────────────┼────────────────┐
          │                │                │
  ┌───────▼──────┐ ┌───────▼──────┐ ┌──────▼──────┐
  │ Elasticsearch │ │   MongoDB    │ │   Gemini    │
  │  (12 indices) │ │  (narratives)│ │  synthesis  │
  └──────────────┘ └──────────────┘ └─────────────┘
```

### 1. Provider abstraction (`base_pipeline.py`)

Every provider implements `BaseIngestionPipeline`, an abstract class with two methods:

- `run_all(query_names, dry_run, end_time, time_window_hours)` — runs all (or a subset of) the 12 signals.
- `run_one(qc: QueryConfig, dry_run)` — runs a single signal and returns an `IngestionResult`.

Shared constants (`QUERY_TO_INDEX`, `QUERY_TO_SIGNAL`, `CADENCE_GROUPS`) live here so every provider references the same signal names and target ES indices.

Selecting a provider at runtime:

```bash
python pipeline_runner.py --provider dune        # default
python pipeline_runner.py --provider defillama
# or via env var
export INGESTION_PROVIDER=defillama
```

### 2. Signal transformer (`signal_transformer.py`)

The transformer is the single normalization layer between any provider's raw output and any downstream store. It has three responsibilities:

**Field mapping** — per-signal mapping functions translate provider-specific field names to canonical names. For example, DefiLlama's `circulating_usd` becomes `total_usd`, `delta_usd` is split into `mint_usd` / `burn_usd`. Dune rows already use canonical names and pass through unchanged.

**Schema enforcement** — after mapping, every document is filtered to the exact field set declared in `DuneIndexManager._INDEX_MAPPINGS`. Any undeclared field is silently dropped before the ES write. This makes `strict_dynamic_mapping_exception` impossible regardless of what a provider returns.

```
canonical field set = _META_FIELDS ∪ _SIGNAL_FIELDS[query_name]
```

The 12 allowed field sets are the single source of truth; Elasticsearch mappings, MongoDB, and Gemini all read from the same normalized output.

**Metadata envelope + deterministic `_id`** — every doc gets `ingested_at`, `query_name`, `signal_category`, `window_start`, `params_snapshot`, and a SHA-256 `_id` derived from the natural key for that signal (e.g. `symbol + window_start` for most, `tx_hash` for whale transactions). The same data ingested twice produces the same `_id`, so re-runs are idempotent upserts.

### 3. Elasticsearch index management (`dune_index_manager.py`)

All 12 signal indices are created once by `DuneIndexManager.ensure_all_indices()` with `dynamic: strict` mappings. On subsequent runs, `ensure_index` calls `put_mapping` to sync any new fields added to the definition without recreating or wiping the index. Shard/replica settings are omitted for Elastic Cloud Serverless compatibility.

### 4. Supported signals per provider

| Signal | Dune | DefiLlama | Notes |
|---|---|---|---|
| `whale_transaction_filter` | SQL | skipped | requires per-tx on-chain data |
| `smart_money_accumulation` | SQL | skipped | requires wallet labels |
| `token_inflow_outflow` | SQL | skipped | requires per-tx on-chain data |
| `bridge_activity` | SQL | `/protocols` (bridge category) | DefiLlama uses TVL delta as flow proxy |
| `wallet_concentration` | SQL | skipped | requires full transfer history |
| `volume_spike_detection` | SQL | `/overview/dexs` | DefiLlama: 24h vol + change_1d |
| `new_holder_growth` | SQL | skipped | requires per-address first-transfer data |
| `dex_trading_concentration` | SQL | `/overview/dexs` | DefiLlama: market share per protocol |
| `post_bridge_deployment` | SQL | skipped | requires per-tx on-chain data |
| `stablecoin_liquidity_flow` | SQL | `/stablecoins` | circulating + prevDay delta |
| `ecosystem_sector_rotation` | SQL | `/protocols` | grouped by category, TVL change |
| `protocol_inflow_leaderboard` | SQL | `/protocol/{slug}` | Aave v3, Lido, EigenLayer TVL delta |

### 5. Adding a new provider

1. Create `app/ingestion/{provider}_pipeline.py` implementing `BaseIngestionPipeline`.
2. In `signal_transformer.py`, add per-signal mapping functions and register them in `_TRANSFORMS["{provider}"]`.
3. Register the provider in `pipeline_runner.py`'s `SUPPORTED_PROVIDERS` and `build_pipeline()`.
4. No changes to ES mappings, MongoDB, or Gemini — the transformer guarantees schema compliance.

### 6. Historical backfill (`backfill.py`)

```bash
python backfill.py --start 2026-03-01 --end 2026-06-01 --provider dune
python backfill.py --start 2026-03-01 --end 2026-06-01 --provider defillama --chunk-days 7
python backfill.py --resume    # skip already-completed chunks (checkpoint in backfill_checkpoint.json)
python backfill.py --dry-run   # print plan without executing
```

Backfill advances in `--chunk-days` windows (default 7 days). Each completed chunk is recorded in `backfill_checkpoint.json` so interrupted runs can resume safely without re-consuming Dune API quota.

---

## Dune Data Ingestion In Elastic

---
1. Index creation — skipped if exists
DuneIndexManager.ensure_index checks HEAD /{index} first. If the index already exists it returns immediately. The index and its mapping are never recreated or wiped.

2. Documents — upserted by deterministic _id
Each document gets a _id computed by _make_doc_id from content-based keys (not ingested_at). es_helpers.bulk uses the default index action, which is an upsert — if a document with that _id already exists it is overwritten in full, otherwise it is created.

3. What the _id is based on, per query:


## Dune Query Mapping



**🔮 Built with ❤️ for crypto researchers and traders**
Your Query,Main Purpose,Key Fields It Should Populate,Category Suggestion,Notes / Output Focus
bridge-activity,Track capital moving between chains,"symbol, from_chain, to_chain, bridge_usd, net_flow_usd, gross_inflow_usd, gross_outflow_usd, total_usd, acceleration_7d_vs_30d_pct, percentage_of_total, time_bucket",capital_migration,Core for Tier 0. Should return directional bridge flows (e.g. Ethereum → Base).
dex-trading-concentration,Measure how concentrated trading activity is,"symbol, dex_share_pct, volume_multiplier, whale_concentration_pct, signals",smart_deployment or ecosystem_rotation,Helps detect if volume is organic or whale-driven.
new-holder-growth,Track organic adoption,"symbol, holder_growth_pct, new_wallets, first_time_users_pct, active_addresses",organic_adoption,Very important for distinguishing whale pumps from real growth.
smart-money-accumulation,Identify sophisticated capital,"symbol, smart_money_usd, smart_money_concentration_pct, whale_usd, net_flow_usd",smart_deployment,Should tag wallets labeled as smart money (use Arkham/Nansen labels in Dune).
token-inflow-outflow,Track net token movement,"symbol, net_flow_usd, gross_inflow_usd, gross_outflow_usd, from_chain, to_chain, signals",capital_migration or token_flows,Broad token flow query. Can feed both bridge and exchange flows.
volume-spike-detection,Detect unusual volume increases,"symbol, volume_multiplier, signals, acceleration_7d_vs_30d_pct",ecosystem_rotation,Good early warning for narrative momentum.
wallet-concentration,Measure how few wallets dominate activity,"symbol, whale_concentration_pct, smart_money_concentration_pct, signals",smart_deployment,"Critical for risk flags (e.g., ""high whale concentration"")."
whale-transaction-filter,Filter large transactions,"symbol, whale_usd, smart_money_usd, signals, total_usd",smart_deployment,Should feed both whale and smart money columns.

┌─────────────────────────────────┬──────────────────────────────┬────────────────────────────┬────────────────────────────────┐
│              File               │          Key tables          │        symbol field        │            Signals             │
├─────────────────────────────────┼──────────────────────────────┼────────────────────────────┼────────────────────────────────┤
│                                 │ bridges_evms.deposits →      │                            │ HIGH_DEPLOYMENT_VOLUME,        │
│ post_bridge_deployment.sql      │ dex.trades (L2s)             │ token bought symbol        │ BROAD_ADOPTION,                │
│                                 │                              │                            │ WHALE_DEPLOYER, HIGH_ACTIVITY  │
├─────────────────────────────────┼──────────────────────────────┼────────────────────────────┼────────────────────────────────┤
│                                 │                              │                            │ NET_MINT_PRESSURE,             │
│ stablecoin_liquidity_flow.sql   │ erc20_ethereum.evt_Transfer  │ USDC/USDT/DAI/FRAX/PYUSD   │ NET_BURN_PRESSURE,             │
│                                 │ (mint/burn)                  │                            │ HIGH_MINT_VOLUME,              │
│                                 │                              │                            │ STRONG_DIRECTIONAL_FLOW        │
├─────────────────────────────────┼──────────────────────────────┼────────────────────────────┼────────────────────────────────┤
│                                 │                              │                            │ STRONG_ROTATION_IN,            │
│ ecosystem_sector_rotation.sql   │ dex.trades + sector lookup   │ sector name (e.g.          │ STRONG_ROTATION_OUT,           │
│                                 │ VALUES CTE                   │ Liquid_Staking)            │ HIGH_SECTOR_VOLUME,            │
│                                 │                              │                            │ ACCELERATING_ROTATION          │
├─────────────────────────────────┼──────────────────────────────┼────────────────────────────┼────────────────────────────────┤
│                                 │                              │                            │ HIGH_PROTOCOL_INFLOW,          │
│ protocol_inflow_leaderboard.sql │ Aave v3 + EigenLayer + Lido  │ protocol name              │ WHALE_DOMINATED,               │
│                                 │ + prices.usd                 │ (Aave_v3/EigenLayer/Lido)  │ BROAD_ADOPTION,                │
│                                 │                              │                            │ ACCELERATING_INFLOW            │
└─────────────────────────────────┴──────────────────────────────┴────────────────────────────┴────────────────────────────────┘


**Helper commands**

1. Compile Python Code after local refractoring
python -m compileall .

2. Compile specific script
python3 -m py_compile scripts/purge.py

 # activate python env
 python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

3. Run Purge
  poetry run python3 app/scripts/purge.py --all             # purge both ES and MongoDB
  poetry run python3 app/scripts/purge.py --elastic         # purge ES indices only
  poetry run python3 app/scripts/purge.py --mongo           # purge MongoDB collections only
  poetry run python3 app/scripts/purge.py --all --dry-run   # preview without deleting


4. Run elastic ingestion
poetry run python3 app/ingestion/dune_pipeline.py
5. Run synthsize
poetry  run python3 app/synthesize/signal_transformer.py --hours 48