"""Quick connectivity check — run this after updating credentials in config.py"""
from brain.config import Config
from elasticsearch import Elasticsearch

print(f"Connecting to: {Config.ES_URL}")

# Try API key first, fall back to basic auth
if Config.ES_API_KEY_ID:
    es = Elasticsearch(Config.ES_URL, api_key=Config.ES_API_KEY_ID)
    auth_method = "API key"
else:
    es = Elasticsearch(Config.ES_URL, basic_auth=(Config.ES_USERNAME, Config.ES_PASSWORD))
    auth_method = "basic auth"

print(f"Auth method: {auth_method}")

try:
    ok = es.ping()
    if ok:
        info = es.info()
        print(f"✅ Connected! Cluster: {info['cluster_name']}, ES version: {info['version']['number']}")

        count = es.count(index="whale_transactions").get("count", "index not found")
        print(f"   whale_transactions docs: {count}")
    else:
        print("❌ Ping returned False — check credentials")
except Exception as e:
    print(f"❌ Error: {e}")
