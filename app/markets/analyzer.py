"""
analyzer.py — Gemini-powered plain-English analysis for top 20 crypto projects.

Completely standalone: zero imports from app.ingestion, app.synthesize, app.brain.

Reads:   MongoDB crypto_markets_config  (CMC price/ranking data)
Writes:  MongoDB crypto_market_analysis (Gemini analysis results)

Usage (CLI):
    python -m app.markets.analyzer              # analyze all 20 projects
    python -m app.markets.analyzer --dry        # print results, skip MongoDB write
    python -m app.markets.analyzer BTC ETH SOL  # analyze specific tickers only
    python -m app.markets.analyzer --fast       # skip roadmap page fetching (uses Gemini knowledge)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import pymongo
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# MongoDB collections (separate from narrative/ingestion collections)
_COLLECTION_CMC      = "crypto_markets_config"    # written by crypto_markets.py
_COLLECTION_ANALYSIS = "crypto_market_analysis"   # written by this module
_DOC_ID              = "top20"

# ---------------------------------------------------------------------------
# Gemini prompts
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are a friendly crypto educator. Your audience is a complete beginner — someone who has \
never owned or studied crypto. Use everyday language. Avoid all jargon. If you must use a \
technical term, explain it immediately in parentheses.

Analyze the crypto project below and return a single JSON object.

PROJECT: {name} ({symbol})
MARKET CAP RANK: #{rank} (rank #{rank} out of ALL crypto projects by total value)
OFFICIAL WEBSITE: {website}
{roadmap_block}

Fill in every field. Return ONLY the raw JSON — no markdown, no code fences, no commentary.

{{
  "description": "<One sentence, max 30 words. What does {name} DO? Explain it like you would to a curious 12-year-old. No crypto jargon.>",

  "ecosystem_category": "<Pick exactly one: L1 | L2 | Sidechain | DeFi | Stablecoin | Oracle | Exchange | Privacy | Interop | Payments | Other>",

  "ecosystem_description": "<One sentence, max 30 words. Where does {name} sit in the crypto world? e.g. 'It is the main blockchain that thousands of other projects are built on top of.'>",

  "trad_fi_equivalent": "<1–6 words. The single closest equivalent in traditional finance or tech — e.g. 'Gold', 'The New York Stock Exchange', 'Visa or Mastercard', 'A central bank', 'Google Play Store'>",

  "trad_fi_explanation": "<One sentence, max 30 words. Why is that a fair comparison? Be specific.>",

  "roadmap_summary": "<Max 90 words. Plain English. What are the 2–3 most important things {name} is working on or planning next? Focus on what this means for everyday users, not developers. No jargon.>",

  "roadmap_source_url": "<The single best URL where someone can read about {name}'s roadmap or upcoming plans — use the roadmap URL if provided, otherwise the main website>",

  "roadmap_source_date": "<Date of this roadmap information as YYYY-MM. Use {today_month} if you are drawing on your training knowledge.>",

  "analysis_confidence": "<high | medium | low — how confident are you that this analysis is accurate?>"
}}
"""

_ROADMAP_BLOCK_WITH_TEXT = """\
ROADMAP URL: {url}
ROADMAP PAGE TEXT (auto-fetched, truncated to 2 500 chars):
---
{text}
---
Use the above page content to answer the roadmap_summary field. If it lists specific upcoming \
features or dates, mention them.
"""

_ROADMAP_BLOCK_URL_ONLY = """\
ROADMAP/WEBSITE URL: {url}
(Could not fetch page content. Use your training knowledge about {name}'s recent roadmap.)
"""

_ROADMAP_BLOCK_NONE = """\
(No roadmap URL available. Use your training knowledge about {name}'s upcoming plans.)
"""


# ---------------------------------------------------------------------------
# Analyzer class
# ---------------------------------------------------------------------------

class MarketAnalyzer:
    """
    Gemini-powered market analyzer. Completely independent — no imports from
    app.ingestion, app.synthesize, or app.brain.
    """

    def __init__(self, mongo_uri: str, mongo_db: str = "kairo"):
        self.mongo_uri = mongo_uri
        self.mongo_db  = mongo_db
        self._client   = None   # Gemini client, lazy-init
        self._model    = None
        self._http     = requests.Session()
        self._http.headers["User-Agent"] = "Mozilla/5.0 (compatible; KairoMarketBot/1.0)"

    # ------------------------------------------------------------------
    # Gemini client (lazy, independent from NarrativeEngine)
    # ------------------------------------------------------------------

    def _init_gemini(self) -> None:
        if self._client:
            return
        from google import genai
        from config.config import Config
        project  = os.getenv("GOOGLE_CLOUD_PROJECT") or Config.GOOGLE_CLOUD_PROJECT
        location = os.getenv("GOOGLE_CLOUD_LOCATION") or Config.GOOGLE_CLOUD_LOCATION
        model    = os.getenv("GEMINI_MODEL")          or Config.GEMINI_MODEL
        if not project:
            raise ValueError("GOOGLE_CLOUD_PROJECT not set — cannot initialise Gemini")
        self._client = genai.Client(vertexai=True, project=project, location=location)
        self._model  = model
        logger.info("Gemini initialised (project=%s, model=%s)", project, model)

    def _call_gemini(self, prompt: str) -> str:
        self._init_gemini()
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
        )
        return getattr(response, "text", "") or ""

    # ------------------------------------------------------------------
    # Roadmap page fetching
    # ------------------------------------------------------------------

    def _fetch_page_text(self, url: str, timeout: int = 6) -> str:
        """Fetch readable text from a URL. Returns empty string on any failure."""
        if not url:
            return ""
        try:
            r = self._http.get(url, timeout=timeout)
            if r.status_code != 200:
                return ""
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:2500]
        except Exception as exc:
            logger.debug("page fetch failed for %s: %s", url, exc)
            return ""

    def _fetch_all_roadmaps_parallel(
        self, projects: list[dict], max_workers: int = 8
    ) -> dict[int, str]:
        """Fetch all roadmap pages in parallel. Returns {cmc_id: page_text}."""
        results: dict[int, str] = {}
        to_fetch = [
            (p["cmc_id"], p.get("roadmap_url") or p.get("website", ""))
            for p in projects
            if p.get("roadmap_url") or p.get("website")
        ]
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self._fetch_page_text, url): cmc_id
                for cmc_id, url in to_fetch
            }
            for fut in as_completed(futures):
                cmc_id = futures[fut]
                try:
                    results[cmc_id] = fut.result()
                except Exception:
                    results[cmc_id] = ""
        return results

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_roadmap_block(
        self, project: dict, page_text: str, fetch_roadmaps: bool
    ) -> str:
        name        = project.get("name", "")
        roadmap_url = project.get("roadmap_url") or project.get("website", "")

        if not fetch_roadmaps:
            if roadmap_url:
                return _ROADMAP_BLOCK_URL_ONLY.format(url=roadmap_url, name=name)
            return _ROADMAP_BLOCK_NONE.format(name=name)

        if page_text:
            return _ROADMAP_BLOCK_WITH_TEXT.format(url=roadmap_url, text=page_text)
        if roadmap_url:
            return _ROADMAP_BLOCK_URL_ONLY.format(url=roadmap_url, name=name)
        return _ROADMAP_BLOCK_NONE.format(name=name)

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(raw: str) -> Optional[dict]:
        text = raw.strip()
        if "```" in text:
            for block in text.split("```"):
                block = block.strip().lstrip("json").strip()
                if block.startswith("{"):
                    text = block
                    break
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start < 0 or end <= 0:
            return None
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            return None

    # ------------------------------------------------------------------
    # Per-project analysis
    # ------------------------------------------------------------------

    def _analyze_one(self, project: dict, roadmap_text: str, fetch_roadmaps: bool) -> dict:
        name        = project.get("name", "")
        symbol      = project.get("symbol", "")
        rank        = project.get("rank", 0)
        website     = project.get("website", "")
        roadmap_url = project.get("roadmap_url") or website
        today_month = datetime.now(timezone.utc).strftime("%Y-%m")

        roadmap_block = self._build_roadmap_block(project, roadmap_text, fetch_roadmaps)

        prompt = _PROMPT_TEMPLATE.format(
            name=name,
            symbol=symbol,
            rank=rank,
            website=website or "(not available)",
            roadmap_block=roadmap_block,
            today_month=today_month,
        )

        result = {
            "cmc_id":               project.get("cmc_id"),
            "symbol":               symbol,
            "name":                 name,
            "analyzed_at":          datetime.now(timezone.utc).isoformat(),
            # Fields Gemini fills in:
            "description":          None,
            "ecosystem_category":   None,
            "ecosystem_description": None,
            "trad_fi_equivalent":   None,
            "trad_fi_explanation":  None,
            "roadmap_summary":      None,
            "roadmap_source_url":   roadmap_url,
            "roadmap_source_date":  today_month,
            "analysis_confidence":  "low",
            "analysis_error":       None,
        }

        try:
            raw     = self._call_gemini(prompt)
            parsed  = self._parse_response(raw)
        except Exception as exc:
            logger.error("Gemini failed for %s: %s", name, exc)
            result["analysis_error"] = str(exc)
            return result

        if parsed:
            result.update({
                "description":           parsed.get("description"),
                "ecosystem_category":    parsed.get("ecosystem_category"),
                "ecosystem_description": parsed.get("ecosystem_description"),
                "trad_fi_equivalent":    parsed.get("trad_fi_equivalent"),
                "trad_fi_explanation":   parsed.get("trad_fi_explanation"),
                "roadmap_summary":       parsed.get("roadmap_summary"),
                "roadmap_source_url":    parsed.get("roadmap_source_url") or roadmap_url,
                "roadmap_source_date":   parsed.get("roadmap_source_date") or today_month,
                "analysis_confidence":   parsed.get("analysis_confidence", "medium"),
            })
        else:
            result["analysis_error"] = "Could not parse Gemini response as JSON"

        return result

    # ------------------------------------------------------------------
    # Batch analysis
    # ------------------------------------------------------------------

    def analyze_all(
        self,
        symbols: Optional[list[str]] = None,
        fetch_roadmaps: bool = True,
        gemini_delay_s: float = 1.5,
        dry_run: bool = False,
        progress_cb=None,
    ) -> list[dict]:
        """
        Analyze all (or a subset of) top-20 projects.

        progress_cb(current: int, total: int, project_name: str) → None
        """
        # ── Load project list from MongoDB ──────────────────────────────────
        mc = pymongo.MongoClient(self.mongo_uri, serverSelectionTimeoutMS=8000)
        doc = mc[self.mongo_db][_COLLECTION_CMC].find_one({"_id": _DOC_ID})
        mc.close()

        if not doc or not doc.get("projects"):
            raise ValueError(
                f"No market data in MongoDB {self.mongo_db}.{_COLLECTION_CMC}. "
                "Run 'python -m app.ingestion.crypto_markets' first."
            )

        projects = doc["projects"]
        if symbols:
            upper = {s.upper() for s in symbols}
            projects = [p for p in projects if p.get("symbol", "").upper() in upper]

        total = len(projects)
        logger.info("Analysing %d project(s)…", total)

        # ── Phase 1: fetch roadmap pages in parallel (saves ~minutes) ───────
        roadmap_texts: dict[int, str] = {}
        if fetch_roadmaps and not dry_run:
            logger.info("Fetching %d roadmap pages in parallel…", total)
            roadmap_texts = self._fetch_all_roadmaps_parallel(projects)

        # ── Phase 2: Gemini calls (sequential, rate-limit safe) ─────────────
        results: list[dict] = []
        for i, project in enumerate(projects):
            name = project.get("name", project.get("symbol", "?"))
            logger.info("[%d/%d] Gemini analysis: %s", i + 1, total, name)

            page_text = roadmap_texts.get(project.get("cmc_id"), "")
            analysis  = self._analyze_one(project, page_text, fetch_roadmaps)
            results.append(analysis)

            if progress_cb:
                progress_cb(i + 1, total, name)

            if i < total - 1:
                time.sleep(gemini_delay_s)

        if not dry_run:
            self._save(results)

        return results

    def _save(self, results: list[dict]) -> None:
        mc = pymongo.MongoClient(self.mongo_uri, serverSelectionTimeoutMS=8000)
        mc[self.mongo_db][_COLLECTION_ANALYSIS].update_one(
            {"_id": _DOC_ID},
            {"$set": {
                "analyzed_at": datetime.now(timezone.utc),
                "projects":    results,
            }},
            upsert=True,
        )
        mc.close()
        logger.info("Saved %d analyses to %s.%s", len(results), self.mongo_db, _COLLECTION_ANALYSIS)

    # ------------------------------------------------------------------
    # Static loader (used by kairo_data.py)
    # ------------------------------------------------------------------

    @staticmethod
    def load_from_mongo(mongo_uri: str, mongo_db: str = "kairo") -> Optional[dict]:
        """Return the analysis document from MongoDB, or None."""
        try:
            mc  = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            doc = mc[mongo_db][_COLLECTION_ANALYSIS].find_one({"_id": _DOC_ID})
            mc.close()
            return doc
        except Exception as exc:
            logger.warning("MarketAnalyzer.load_from_mongo: %s", exc)
            return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
    from dotenv import load_dotenv
    load_dotenv()
    from config.config import Config

    dry_run      = "--dry"  in sys.argv
    fast_mode    = "--fast" in sys.argv
    symbols      = [a.upper() for a in sys.argv[1:] if not a.startswith("--")]

    if dry_run:
        logger.info("DRY RUN — results will not be saved to MongoDB")
    if fast_mode:
        logger.info("FAST MODE — skipping roadmap page fetching")

    mongo_uri = os.getenv("MONGO_URI") or Config.MONGO_URI
    mongo_db  = os.getenv("MONGO_DB")  or Config.MONGO_DB or "kairo"

    if not mongo_uri:
        print("ERROR: MONGO_URI not configured")
        sys.exit(1)

    analyzer = MarketAnalyzer(mongo_uri, mongo_db)

    def _cb(current, total, name):
        print(f"  [{current:>2}/{total}] ✓ {name}")

    results = analyzer.analyze_all(
        symbols=symbols or None,
        fetch_roadmaps=not fast_mode,
        dry_run=dry_run,
        progress_cb=_cb,
    )

    print(f"\n{'#':>3}  {'Sym':<8}  {'Ecosystem':<14}  {'TradFi':<24}  Conf   Status")
    print("─" * 75)
    for r in results:
        err  = "❌" if r.get("analysis_error") else "✓"
        eco  = r.get("ecosystem_category") or "—"
        trad = (r.get("trad_fi_equivalent") or "—")[:23]
        conf = r.get("analysis_confidence") or "—"
        print(f"  {r.get('symbol','?'):<8}  {eco:<14}  {trad:<24}  {conf:<6} {err}")

    print(f"\nTotal: {len(results)} projects")
    if not dry_run:
        print(f"Saved → MongoDB: {mongo_db}.{_COLLECTION_ANALYSIS}")


if __name__ == "__main__":
    _cli_main()
