⚡ QUICK START GUIDE

This guide will get you up and running in 5 minutes.

## Prerequisites

- Python 3.9+
- Elasticsearch instance (cloud or local)
- Google Gemini API key
- Git

## 1️⃣ Clone & Setup (2 min)

```bash
# Clone the repository
git clone https://github.com/yourusername/KairoAgent.git
cd KairoAgent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## 2️⃣ Configure Credentials (1 min)

### Option A: Secrets File (Recommended for Streamlit)

Create `.streamlit/secrets.toml`:

```toml
# Get from Elasticsearch
ES_URL = "https://your-es-instance.es.region.gcp.elastic.cloud:443"
ES_USERNAME = "elastic"
ES_PASSWORD = "your-password"

# Get from Google Cloud
GEMINI_KEY = "your-gemini-api-key"
```

### Option B: Environment Variables

```bash
export ES_URL="https://your-es-instance.es.region.gcp.elastic.cloud:443"
export ES_USERNAME="elastic"
export ES_PASSWORD="your-password"
export GEMINI_KEY="your-gemini-api-key"
```

## 3️⃣ Load Data (1 min)

Ingest sample whale transaction data:

```bash
python ingest.py
```

You should see:
```
✅ Ingested 3 whale transactions into Elasticsearch
```

## 4️⃣ Run the App (1 min)

```bash
streamlit run app.py
```

The app opens at: **http://localhost:8501**

## 5️⃣ Try It Out!

1. **Go to "🔍 Detect Narratives"** tab
2. **Click "🔍 Detect Emerging Narratives"** button
3. **Wait for analysis** (takes ~10 seconds)
4. **See detected narratives** with confidence scores
5. **Click "⭐ Track"** on any narrative to monitor it

## 📊 Available Features

| Tab | What it does |
|-----|-------------|
| 🔍 Detect | Find new narratives from whale activity |
| 📊 Dashboard | Overview of all narratives + stats |
| ⭐ Tracked | Monitor narratives you care about |
| 📈 History | See how narratives have evolved |

## 🧪 Test Without UI

Run the example script to test all components:

```bash
python example.py
```

This will:
1. ✓ Load whale data
2. ✓ Detect narratives
3. ✓ Track narratives
4. ✓ Show history
5. ✓ Display stats

## 🐛 Troubleshooting

### "Connection refused" error?
```
Check your Elasticsearch URL and credentials in .streamlit/secrets.toml
```

### "API Error" from Gemini?
```
Make sure your GEMINI_KEY is valid and has no typos
```

### "No narratives detected"?
```
Run: python ingest.py
Make sure data/transactions.json has entries
```

### Port 8501 already in use?
```
streamlit run app.py --server.port 8502
```

## 📚 Next Steps

1. **Add your own data**: Edit `data/transactions.json`
2. **Deploy**: See [DEPLOYMENT.md](DEPLOYMENT.md)
3. **Customize**: See [ARCHITECTURE.md](ARCHITECTURE.md)
4. **Integrate**: See [README.md](README.md)

## 🚀 Production Ready?

When ready to deploy:

```bash
# 1. Create .env file (don't commit!)
cp .env.example .env

# 2. Choose deployment option
#    - Docker: docker build -t narrative-agent .
#    - Streamlit Cloud: git push to GitHub
#    - AWS/GCP: See DEPLOYMENT.md

# 3. Set up monitoring and alerts

# 4. Scale as needed
```

## 💡 Common Workflows

### Detect Narratives Every Hour
```bash
# Add to crontab
0 * * * * cd /path/to/KairoAgent && python example.py
```

### Backup Data Weekly
```bash
# Backup Elasticsearch
python -c "from elasticsearch import Elasticsearch; ..."
```

### Monitor Costs
```bash
# Track Gemini API usage
python -c "import google.generativeai; ..."
```

## 📖 Full Documentation

- **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
- **Deployment**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **API Reference**: [README.md#-api-reference](README.md#-api-reference)

## 🎯 Sample Data

The default `data/transactions.json` contains 3 whale transactions:

```json
[
  { "wallet": "0xA1", "token": "FET", "category": "AI", "action": "BUY", "amount_usd": 250000 },
  { "wallet": "0xB7", "token": "AGIX", "category": "AI", "action": "BUY", "amount_usd": 180000 },
  { "wallet": "0xC2", "token": "AXS", "category": "Gaming", "action": "SELL", "amount_usd": 95000 }
]
```

This is enough to detect an "AI Agent Accumulation" narrative!

---

**🔮 You're all set! Happy narrative hunting!**
