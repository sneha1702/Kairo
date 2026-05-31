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
## Dune Data Ingestion In Elastic

---
1. Index creation — skipped if exists
DuneIndexManager.ensure_index checks HEAD /{index} first. If the index already exists it returns immediately. The index and its mapping are never recreated or wiped.

2. Documents — upserted by deterministic _id
Each document gets a _id computed by _make_doc_id from content-based keys (not ingested_at). es_helpers.bulk uses the default index action, which is an upsert — if a document with that _id already exists it is overwritten in full, otherwise it is created.

3. What the _id is based on, per query:

┌───────────────────────────┬────────────────────┐


**🔮 Built with ❤️ for crypto researchers and traders**


**Helper commands**

1. Compile Python Code after local refractoring
python -m compileall .
