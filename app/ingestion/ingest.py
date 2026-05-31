import json
import logging
from pathlib import Path
from app.brain.elasticsearch_manager import ElasticsearchManager
from app.brain.config import Config

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def ingest_static_transactions() -> None:
    es_manager = ElasticsearchManager(
        Config.ES_URL,
        Config.ES_USERNAME,
        Config.ES_PASSWORD,
        Config.ES_API_KEY_ID,
    )

    data_path = Path(__file__).resolve().parent / "data" / "transactions.json"
    logger.info(f"Script location: {Path(__file__).resolve()}")
    logger.info(f"Attempting to load transactions from: {data_path}")
    logger.info(f"File exists: {data_path.exists()}")
    
    if not data_path.exists():
        logger.error(f"File not found: {data_path}")
        raise FileNotFoundError(f"Data file not found: {data_path}")
    
    with open(data_path) as f:
        data = json.load(f)

    es_manager.ingest_transactions(data)
    logger.info(f"✅ Ingested {len(data)} whale transactions into Elasticsearch")


    es_manager.ingest_transactions(data)
    logger.info(f"✅ Ingested {len(data)} whale transactions into Elasticsearch")


if __name__ == "__main__":
    ingest_static_transactions()
