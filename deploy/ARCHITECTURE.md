# 🏗️ Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                                                               │
│                    User Interface Layer                       │
│                   (Streamlit Dashboard)                       │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  • Detect Narratives (Real-time Detection)           │   │
│  │  • Dashboard (Statistics & Overview)                 │   │
│  │  • Tracked Narratives (User Watchlist)               │   │
│  │  • History (Time-series Trends)                      │   │
│  └──────────────────────────────────────────────────────┘   │
│                         ▲                                     │
│                         │                                     │
└────────────────────────┼─────────────────────────────────────┘
                         │
                         │ REST API / Direct Access
                         │
┌────────────────────────▼─────────────────────────────────────┐
│                                                               │
│              Application Logic Layer                          │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  NarrativeEngine                                     │    │
│  │  • group_whale_activity()                           │    │
│  │  • detect_narratives() - Uses Gemini               │    │
│  │  • calculate_narrative_momentum()                   │    │
│  │  • enrich_narrative() - Add metadata                │    │
│  └─────────────────────────────────────────────────────┘    │
│                         │                                     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  NarrativeTracker                                    │    │
│  │  • save_narratives()                                │    │
│  │  • get_current_narratives()                         │    │
│  │  • track_narrative()                                │    │
│  │  • get_narrative_history()                          │    │
│  │  • get_narrative_stats()                            │    │
│  └─────────────────────────────────────────────────────┘    │
│                         │                                     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ElasticsearchManager                               │    │
│  │  • ingest_transactions()                            │    │
│  │  • get_recent_transactions()                        │    │
│  │  • get_category_activity()                          │    │
│  │  • get_top_active_whales()                          │    │
│  │  • get_emerging_tokens()                            │    │
│  └─────────────────────────────────────────────────────┘    │
│                         │                                     │
└────────────────────────┼─────────────────────────────────────┘
                         │
                ┌────────┴────────┬────────────┐
                │                 │            │
                ▼                 ▼            ▼
        ┌──────────────┐  ┌──────────────┐  ┌─────────────┐
        │ Elasticsearch│  │ Google       │  │ On-Chain    │
        │              │  │ Gemini API   │  │ Data Source │
        │ • whale_     │  │              │  │             │
        │   transactions│  │ • Detects    │  │ • Whale     │
        │              │  │   narratives │  │   wallets   │
        │ • narratives │  │ • Scores     │  │ • Tokens    │
        │              │  │   confidence │  │ • Volume    │
        │ • narrative_ │  │ • Generates  │  │             │
        │   history    │  │   insights   │  │             │
        └──────────────┘  └──────────────┘  └─────────────┘
```

## Component Details

### 1. User Interface (Streamlit)

**File**: `app.py`

Four main tabs:

1. **🔍 Detect Narratives**
   - Real-time detection from whale activity
   - Display detected narratives with confidence scores
   - Track narratives from here
   - View detailed analysis

2. **📊 Narrative Dashboard**
   - Overview statistics
   - List of all narratives
   - Strengthening narratives
   - Quick access to tracking

3. **⭐ Tracked Narratives**
   - User's watchlist
   - 7-day trend charts
   - Untrack option
   - Historical performance

4. **📈 Narrative History**
   - Deep dive into narrative evolution
   - Confidence and momentum trends
   - Statistical analysis

### 2. NarrativeEngine (Core Logic)

**File**: `narrative_engine.py`

Key methods:

```python
class NarrativeEngine:
    def group_whale_activity(transactions) -> Dict
        # Groups whale transactions by category
        # Calculates buy/sell ratios
        # Returns structured activity summary

    def detect_narratives(whale_activity, historical=None) -> List[Dict]
        # Calls Gemini to analyze patterns
        # Returns list of narratives with metadata
        # Uses historical context for momentum

    def calculate_narrative_momentum(current, previous) -> Dict
        # Compares current vs historical data
        # Returns trend: strengthening/weakening/stable
        # Calculates momentum score

    def enrich_narrative(narrative, previous=None) -> Dict
        # Adds momentum data
        # Includes historical context
        # Returns enriched narrative
```

### 3. NarrativeTracker (Persistence)

**File**: `narrative_tracker.py`

Manages Elasticsearch indices:

- **`narratives`**: Current active narratives
  - Updated when new narratives detected
  - Tracks user interest (tracked field)
  - Stores confidence and momentum

- **`narrative_history`**: Time-series data
  - Append-only (new records per detection)
  - Tracks confidence changes over time
  - Enables trend analysis

Key methods:

```python
class NarrativeTracker:
    def save_narratives(narratives, user_id)
        # Saves to both current and history indices

    def get_current_narratives(user_id, min_confidence=0.5)
        # Returns active narratives for user

    def get_narrative_history(name, days=7, user_id)
        # Returns time-series data

    def track_narrative(name, user_id)
        # Marks narrative as tracked

    def get_narrative_stats(user_id)
        # Returns aggregate statistics
```

### 4. ElasticsearchManager (Data Access)

**File**: `elasticsearch_manager.py`

Handles all Elasticsearch operations:

```python
class ElasticsearchManager:
    def get_recent_transactions(hours, min_usd)
        # Retrieves whale transactions

    def get_category_activity(hours)
        # Aggregates by category

    def get_top_active_whales(hours, limit)
        # Finds most active wallets

    def get_emerging_tokens(hours, min_transactions)
        # Identifies tokens with sudden activity
```

## Data Flow

### Detection Flow

```
User clicks "Detect" 
    ↓
Get recent whale transactions (ES)
    ↓
Group by category/token
    ↓
Format for Gemini analysis
    ↓
Call Gemini API
    ↓
Parse response JSON
    ↓
Calculate momentum
    ↓
Save to narratives + history (ES)
    ↓
Display to user
```

### Tracking Flow

```
User clicks "Track"
    ↓
Update narrative "tracked" field
    ↓
User views tracked narratives
    ↓
Fetch from narratives index
    ↓
Get 7-day history
    ↓
Display trends
```

## Data Structures

### Whale Transaction

```json
{
  "wallet": "0xA1...",
  "token": "FET",
  "category": "AI",
  "action": "BUY",
  "amount_usd": 250000,
  "timestamp": "2026-05-25T10:00:00",
  "chain": "ethereum",
  "tx_hash": "0xabc...",
  "price_impact": 0.02,
  "slippage": 0.01
}
```

### Detected Narrative

```json
{
  "name": "AI Agent Infrastructure Surge",
  "category": "AI",
  "strength": "High",
  "momentum": "Strengthening",
  "confidence_score": 0.85,
  "momentum": {
    "trend": "strengthening",
    "momentum_score": 0.72,
    "strength_change": 1,
    "confidence_change": 0.15
  },
  "key_evidence": [
    "Two major whale accumulations",
    "430k USD in net buys"
  ],
  "implications": "Market may rally on AI thesis",
  "top_tokens": ["FET", "AGIX", "RENDER"],
  "retail_considerations": "Consider AI exposure",
  "detected_at": "2026-05-25T12:00:00",
  "tracked": false,
  "user_id": "default"
}
```

### Narrative History Record

```json
{
  "narrative_name": "AI Agent Infrastructure Surge",
  "category": "AI",
  "strength": "High",
  "confidence_score": 0.85,
  "momentum_score": 0.72,
  "recorded_at": "2026-05-25T12:00:00",
  "user_id": "default"
}
```

## Elasticsearch Indices

### Index: `whale_transactions`

```
Properties:
  wallet (keyword) - whale address
  token (keyword) - token symbol
  category (keyword) - AI, Gaming, DeFi, etc
  action (keyword) - BUY or SELL
  amount_usd (float) - USD value
  amount_tokens (float) - token quantity
  timestamp (date) - transaction time
  chain (keyword) - blockchain
  tx_hash (keyword) - transaction hash
  price_impact (float) - market impact %
  slippage (float) - slippage %
```

### Index: `narratives`

```
Properties:
  name (keyword) - narrative title
  category (keyword) - primary category
  strength (keyword) - High/Medium/Low
  confidence_score (float) - 0.0-1.0
  momentum (object) - nested momentum data
  detected_at (date) - detection timestamp
  updated_at (date) - last update
  tracked (boolean) - user tracking
  user_id (keyword) - user identifier
  key_evidence (text) - supporting evidence
  top_tokens (keyword) - featured tokens
```

### Index: `narrative_history`

```
Properties:
  narrative_name (keyword)
  category (keyword)
  strength (keyword)
  confidence_score (float)
  momentum_score (float)
  recorded_at (date) - timestamp of record
  user_id (keyword)

Time-series design:
  New documents appended per detection
  Query by narrative_name + time range
  Enables trend analysis
```

## API Integration

### Google Gemini API

**Model**: `gemini-1.5-flash`

**Purpose**: Narrative detection and analysis

**Typical Flow**:
```
Input: Whale activity summary
Prompt: Structured narrative detection
Output: JSON with 3-5 narratives
```

**Cost Considerations**:
- Input tokens: ~500-1000 per detection
- Output tokens: ~500-1000 per detection
- Free tier: 60 requests/minute

## Security Architecture

1. **Secrets Management**
   - Store in `.streamlit/secrets.toml` (dev)
   - AWS Secrets Manager / GCP Secret Manager (prod)
   - Environment variables as fallback

2. **Authentication**
   - Elasticsearch: Basic auth (username/password)
   - Gemini API: API key only
   - Optional: Add user authentication layer

3. **Data Privacy**
   - User-scoped narratives (`user_id`)
   - No sensitive data stored
   - SSL/TLS for all connections

## Scalability Considerations

### Horizontal Scaling

1. **Multiple Streamlit Instances**
   - Load balance with ALB
   - Share Elasticsearch backend
   - Session management needed

2. **Elasticsearch Scaling**
   - Increase shards for write throughput
   - Increase replicas for read performance
   - Index lifecycle management (ILM) for history

3. **Caching Layer**
   - Cache whale activity aggregations
   - Cache detected narratives (1 hour)
   - Redis for session storage

### Vertical Scaling

1. **Memory**: Increase for larger datasets
2. **CPU**: Multi-core for parallel processing
3. **Disk**: SSD for Elasticsearch performance

## Performance Optimization

1. **Query Optimization**
   - Use filter context (keyword fields)
   - Aggregate at query time
   - Limit result sets

2. **Caching Strategy**
   - Cache recent transactions (1 hour)
   - Cache narrative detections (4 hours)
   - Use Redis for distributed cache

3. **API Optimization**
   - Batch Gemini requests
   - Reuse connections
   - Implement exponential backoff

## Monitoring & Observability

1. **Key Metrics**
   - Narratives detected per day
   - Average confidence score
   - API latency (ES, Gemini)
   - User engagement

2. **Logging**
   - Request/response logging
   - Error tracking
   - API quota monitoring

3. **Alerts**
   - ES connectivity failures
   - Gemini API errors
   - Unusual detection patterns
   - High resource usage

## Future Enhancements

1. **Real-time Updates**
   - WebSocket for live updates
   - Pub/sub for narrative changes
   - Push notifications

2. **Advanced Analytics**
   - Correlation analysis
   - Cross-chain narratives
   - Social sentiment integration

3. **ML Improvements**
   - Custom classifier training
   - Anomaly detection
   - Predictive analytics

4. **Integration**
   - Trading bots
   - Portfolio tracking
   - Risk management
