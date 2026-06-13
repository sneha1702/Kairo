"""
crypto_markets.py — Fetches top 20 crypto projects from CoinMarketCap (free tier)
and stores performance + roadmap config in MongoDB collection `crypto_markets_config`.

Usage (CLI):
    python -m app.ingestion.crypto_markets          # full update — fetches + saves to MongoDB
    python -m app.ingestion.crypto_markets --dry    # print results, skip MongoDB write
    python -m app.ingestion.crypto_markets --no-roadmap  # skip roadmap discovery (faster)

Environment vars:
    CMC_API_KEY   — CoinMarketCap free-tier key (https://coinmarketcap.com/api/)
    MONGO_URI     — MongoDB Atlas connection string
    MONGO_DB      — Database name (default: kairo)
"""

from __future__ import annotations

import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import certifi
import pymongo
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

CMC_BASE = "https://pro-api.coinmarketcap.com"

# Common roadmap paths to probe before scraping the home page
_ROADMAP_PATHS = [
    "/roadmap",
    "/en/roadmap",
    "/about/roadmap",
    "/docs/roadmap",
    "/developers/roadmap",
    "/community/roadmap",
    "/plan",
    "/plans",
]

COLLECTION = "crypto_markets_config"
DOC_ID = "top20"


class CryptoMarketsUpdater:
    def __init__(self, cmc_api_key: str, mongo_uri: str, mongo_db: str = "kairo"):
        self.api_key = cmc_api_key
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db
        self._session = requests.Session()
        self._session.headers.update({
            "X-CMC_PRO_API_KEY": cmc_api_key,
            "Accept": "application/json",
            "User-Agent": "KairoAgent/1.0",
        })

    # ------------------------------------------------------------------
    # CMC API calls
    # ------------------------------------------------------------------

    def _cmc_get(self, path: str, params: dict) -> dict:
        resp = self._session.get(CMC_BASE + path, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def fetch_top20_listings(self) -> list[dict]:
        """Fetch top 20 by market cap with 1d / 7d / 30d % changes."""
        data = self._cmc_get("/v1/cryptocurrency/listings/latest", {
            "limit": 20,
            "convert": "USD",
            "sort": "market_cap",
        })
        return data.get("data", [])

    def fetch_project_info(self, cmc_ids: list[int]) -> dict[int, dict]:
        """Fetch metadata (website URLs, logo) for the given CMC IDs."""
        data = self._cmc_get("/v1/cryptocurrency/info", {
            "id": ",".join(str(i) for i in cmc_ids),
        })
        return {int(k): v for k, v in data.get("data", {}).items()}

    def fetch_global_market_cap(self) -> float:
        """Return total crypto market cap in USD from CMC global metrics."""
        try:
            data = self._cmc_get("/v1/global-metrics/quotes/latest", {"convert": "USD"})
            return float(
                data.get("data", {}).get("quote", {}).get("USD", {}).get("total_market_cap") or 0
            )
        except Exception as exc:
            logger.warning("fetch_global_market_cap failed: %s", exc)
            return 0.0

    # ------------------------------------------------------------------
    # Roadmap discovery
    # ------------------------------------------------------------------

    def _discover_roadmap(self, website: str) -> Optional[str]:
        """
        Try to find a roadmap URL for the given official website.
        1. Probe common paths (/roadmap, /en/roadmap, …) with HEAD requests.
        2. Fall back to scraping the home page for <a href=*roadmap*> links.
        Returns the discovered URL or None if nothing found.
        """
        if not website:
            return None
        base = website.rstrip("/")
        probe_session = requests.Session()
        probe_session.headers["User-Agent"] = "Mozilla/5.0 (compatible; KairoBot/1.0)"

        # Phase 1 — probe common paths
        for path in _ROADMAP_PATHS:
            try:
                r = probe_session.head(base + path, timeout=4, allow_redirects=True)
                if r.status_code < 400:
                    return base + path
            except Exception:
                continue

        # Phase 2 — scrape home page for roadmap anchors
        try:
            r = probe_session.get(base, timeout=7)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = str(a["href"])
                    text = a.get_text(strip=True).lower()
                    if "roadmap" in href.lower() or "roadmap" in text:
                        if href.startswith("http"):
                            return href
                        if href.startswith("/"):
                            return base + href
        except Exception:
            pass

        return None

    def _discover_roadmap_parallel(self, projects_with_website: list[tuple[int, str]]) -> dict[int, Optional[str]]:
        """Discover roadmap URLs in parallel (max 6 threads)."""
        results: dict[int, Optional[str]] = {}
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(self._discover_roadmap, url): cmc_id
                       for cmc_id, url in projects_with_website}
            for fut in as_completed(futures):
                cmc_id = futures[fut]
                try:
                    results[cmc_id] = fut.result()
                except Exception as exc:
                    logger.debug("roadmap future error for id %s: %s", cmc_id, exc)
                    results[cmc_id] = None
        return results

    # ------------------------------------------------------------------
    # Main build
    # ------------------------------------------------------------------

    def build_projects(self, discover_roadmaps: bool = True) -> list[dict]:
        """Fetch all data and return the project list."""
        logger.info("Fetching top 20 listings from CoinMarketCap…")
        listings = self.fetch_top20_listings()

        cmc_ids = [item["id"] for item in listings]
        logger.info("Fetching metadata + global market cap…")
        info_map, total_mcap = (
            self.fetch_project_info(cmc_ids),
            self.fetch_global_market_cap(),
        )

        # Build base project records
        projects: list[dict] = []
        for rank, item in enumerate(listings, 1):
            cmc_id = item["id"]
            quote = item.get("quote", {}).get("USD", {})
            info = info_map.get(cmc_id, {})
            websites = info.get("urls", {}).get("website") or []
            website = websites[0] if websites else ""
            logo_url = info.get("logo") or f"https://s2.coinmarketcap.com/static/img/coins/64x64/{cmc_id}.png"
            project_mcap = float(quote.get("market_cap") or 0)
            market_share = round(project_mcap / total_mcap * 100, 3) if total_mcap > 0 else 0.0
            projects.append({
                "rank": rank,
                "cmc_id": cmc_id,
                "symbol": item.get("symbol", ""),
                "name": item.get("name", ""),
                "slug": item.get("slug", ""),
                "price_usd": float(quote.get("price") or 0),
                "perf_1d": float(quote.get("percent_change_24h") or 0),
                "perf_7d": float(quote.get("percent_change_7d") or 0),
                "perf_30d": float(quote.get("percent_change_30d") or 0),
                "market_cap": project_mcap,
                "market_share_pct": market_share,
                "volume_24h": float(quote.get("volume_24h") or 0),
                "website": website,
                "roadmap_url": None,
                "roadmap_url_auto": False,
                "logo_url": logo_url,
                "cmc_last_updated": item.get("last_updated", ""),
            })

        # Roadmap discovery
        if discover_roadmaps:
            logger.info("Discovering roadmap URLs (parallel, up to 6 threads)…")
            to_probe = [(p["cmc_id"], p["website"]) for p in projects if p["website"]]
            roadmap_map = self._discover_roadmap_parallel(to_probe)
            for p in projects:
                found = roadmap_map.get(p["cmc_id"])
                p["roadmap_url"] = found or p["website"]
                p["roadmap_url_auto"] = found is not None
        else:
            for p in projects:
                p["roadmap_url"] = p["website"]

        return projects

    def save_to_mongo(self, projects: list[dict]) -> None:
        client = pymongo.MongoClient(self.mongo_uri, tlsCAFile=certifi.where())
        db = client[self.mongo_db]
        db[COLLECTION].update_one(
            {"_id": DOC_ID},
            {"$set": {
                "updated_at": datetime.now(timezone.utc),
                "projects": projects,
            }},
            upsert=True,
        )
        client.close()
        logger.info("Saved %d projects to %s.%s", len(projects), self.mongo_db, COLLECTION)

    def update(self, discover_roadmaps: bool = True, dry_run: bool = False) -> list[dict]:
        """Full update: fetch → build → save to MongoDB."""
        projects = self.build_projects(discover_roadmaps=discover_roadmaps)
        if not dry_run:
            self.save_to_mongo(projects)
        return projects

    # ------------------------------------------------------------------
    # Static loader (used by kairo_data.py at serve time)
    # ------------------------------------------------------------------

    @staticmethod
    def load_from_mongo(mongo_uri: str, mongo_db: str = "kairo") -> Optional[dict]:
        """Return the stored top20 config document, or None if absent."""
        try:
            client = pymongo.MongoClient(mongo_uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=2000)
            doc = client[mongo_db][COLLECTION].find_one({"_id": DOC_ID})
            client.close()
            return doc
        except Exception as exc:
            logger.warning("load_from_mongo failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    import os
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from dotenv import load_dotenv
    load_dotenv(override=True)
    from config.config import Config

    dry_run = "--dry" in sys.argv
    no_roadmap = "--no-roadmap" in sys.argv

    if dry_run:
        logger.info("DRY RUN — data will not be saved to MongoDB")

    cmc_key = os.getenv("CMC_API_KEY") or getattr(Config, "CMC_API_KEY", "")
    if not cmc_key:
        print(
            "\nERROR: CMC_API_KEY is not set.\n"
            "  1. Get a free key at: https://coinmarketcap.com/api/\n"
            "  2. Add it to your .env:  CMC_API_KEY = \"your_key_here\"\n"
        )
        sys.exit(1)

    mongo_uri = os.getenv("MONGO_URI") or Config.MONGO_URI
    mongo_db  = os.getenv("MONGO_DB")  or Config.MONGO_DB or "kairo"

    updater = CryptoMarketsUpdater(cmc_key, mongo_uri, mongo_db)
    projects = updater.update(discover_roadmaps=not no_roadmap, dry_run=dry_run)

    print(f"\n{'#':>3}  {'Symbol':<8}  {'Name':<22}  {'Share':>7}  {'1d':>9}  {'7d':>9}  {'30d':>10}  Activity URL")
    print("-" * 100)
    for p in projects:
        share = f"{p.get('market_share_pct', 0):.2f}%"
        url_tag = "✓" if p.get("roadmap_url_auto") else ("site" if p.get("roadmap_url") else "—")
        print(
            f"{p['rank']:>3}  {p['symbol']:<8}  {p['name']:<22}  {share:>7}  "
            f"{p['perf_1d']:>+8.2f}%  {p['perf_7d']:>+8.2f}%  {p['perf_30d']:>+9.2f}%  {url_tag}"
        )

    print(f"\nTotal: {len(projects)} projects")
    if not dry_run:
        print(f"Saved to MongoDB: {mongo_db}.{COLLECTION}")


if __name__ == "__main__":
    _cli_main()
