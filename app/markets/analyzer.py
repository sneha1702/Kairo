"""
analyzer.py — Gemini-powered analysis for top 20 crypto projects.

Fetches latest releases, news, and roadmap pages per project, then uses Gemini
to generate plain-English summaries covering: what the project does, where it
fits in crypto, its traditional-finance equivalent, and its latest activity
(releases shipped, news published, what's planned next).

Standalone: no imports from app.ingestion, app.synthesize, or app.brain.

Reads:   MongoDB crypto_markets_config   (CMC price/ranking data)
Writes:  MongoDB crypto_market_analysis  (Gemini analysis results)

Usage:
    python -m app.markets.analyzer              # analyze all 20 projects
    python -m app.markets.analyzer --dry        # print results, skip MongoDB write
    python -m app.markets.analyzer BTC ETH SOL  # analyze specific tickers only
    python -m app.markets.analyzer --fast       # skip page fetching (Gemini knowledge only)
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

_COLLECTION_CMC      = "crypto_markets_config"
_COLLECTION_ANALYSIS = "crypto_market_analysis"
_DOC_ID              = "top20"

# ---------------------------------------------------------------------------
# URL path probing lists (tried with HEAD, first hit wins per category)
# ---------------------------------------------------------------------------

_RELEASES_PATHS = [
    "/releases", "/en/releases",
    "/changelog", "/en/changelog",
    "/versions", "/release-notes",
    "/downloads",
]
_NEWS_PATHS = [
    "/news", "/en/news",
    "/blog", "/en/blog",
    "/updates", "/announcements",
    "/press", "/media",
]
_ROADMAP_PATHS = [
    "/roadmap", "/en/roadmap",
    "/about/roadmap", "/docs/roadmap",
    "/community/roadmap", "/plan", "/plans",
]

# ---------------------------------------------------------------------------
# Gemini prompt
# ---------------------------------------------------------------------------

_PROMPT = """\
You are a friendly crypto journalist writing for readers who have never owned crypto.
Use simple, everyday English. Avoid all jargon. If a technical term is unavoidable,
explain it in plain words right afterwards.

Analyze the crypto project below and return ONE JSON object.

PROJECT: {name} ({symbol})
MARKET CAP RANK: #{rank}
OFFICIAL WEBSITE: {website}

{pages_block}

Return ONLY the raw JSON — no markdown, no code fences, no extra text.

{{
  "display_name": "<The full commonly-known name people use for this project. Examples: BNB → 'Binance Coin', XRP → 'Ripple', ADA → 'Cardano', DOT → 'Polkadot', AVAX → 'Avalanche', LINK → 'Chainlink', TRX → 'TRON', TON → 'Toncoin'. If the CMC name is already the well-known common name (Bitcoin, Ethereum, Tether, Solana, etc.), repeat it unchanged.>",

  "description": "<One sentence, max 30 words. What does {name} DO? Explain it like the reader is 12 and has never heard of crypto.>",

  "ecosystem_category": "<Exactly one: L1 | L2 | Sidechain | DeFi | Stablecoin | Oracle | Exchange | Privacy | Interop | Payments | Other>",

  "ecosystem_description": "<One sentence, max 30 words. Where does {name} sit in the crypto ecosystem? e.g. 'It is the main blockchain that thousands of other apps are built on top of.'>",

  "trad_fi_equivalent": "<1–6 words. The closest traditional-finance or technology equivalent — e.g. 'Gold', 'The New York Stock Exchange', 'Visa or Mastercard', 'A central bank', 'Google Play Store'>",

  "trad_fi_explanation": "<One sentence, max 30 words. Why is that a fair comparison? Be specific.>",

  "latest_release": "<Most recent release or version number with approximate date if known, e.g. 'v27.0 (Apr 2024)' or 'Dencun upgrade (Mar 2024)'. Write null if not a versioned-software project.>",

  "latest_news_headline": "<One sentence: the single most recent and important thing that happened — a launch, upgrade, partnership, milestone, or policy change. Use page content if available, else your training knowledge.>",

  "activity_summary": "<Max 90 words. Plain English. Cover: (1) what they shipped or announced most recently, (2) what is actively being built or tested right now, (3) what is planned next. Focus on what this means for users, not developers. No jargon.>",

  "activity_source_url": "<IMPORTANT: Return the DIRECT URL of this project's releases, news, blog, or roadmap page — NOT the homepage. Use your training knowledge to find the correct page. Examples: Bitcoin → 'https://bitcoin.org/en/releases/', Ethereum → 'https://ethereum.org/en/history/', Tether → 'https://tether.io/news/', Solana → 'https://solana.com/news', BNB Chain → 'https://www.bnbchain.org/en/blog', Ripple → 'https://ripple.com/insights/', Cardano → 'https://roadmap.cardano.org'. If a fetched page URL is shown above and it is specifically a news/releases/roadmap page (not a redirect to the homepage), prefer that URL. If you are genuinely uncertain, return the main website URL.>",

  "activity_source_date": "<Date of this information as YYYY-MM. Use {today_month} if drawing on your training knowledge.>",

  "analysis_confidence": "<high | medium | low — how confident are you that this analysis is accurate?>"
}}
"""

# Different page-block templates depending on what was fetched
_PAGES_WITH_CONTENT = """\
FETCHED PAGES (auto-fetched — use this content to fill activity fields):

{sections}

Use the above content where available. For anything not covered, draw on your training knowledge.\
"""

_PAGES_NO_CONTENT = """\
(Page fetching was skipped or failed. Draw on your training knowledge about {name}'s \
most recent releases, news, and upcoming plans.)\
"""


# ---------------------------------------------------------------------------
# Thread-safe page fetcher (module-level — no shared session)
# ---------------------------------------------------------------------------

def _fetch_text(url: str, timeout: int = 5) -> str:
    """Fetch readable text from a URL. Thread-safe (new request per call)."""
    if not url:
        return ""
    try:
        r = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KairoBot/1.0)"},
        )
        if r.status_code != 200:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return ""


def _probe_first(base: str, paths: list[str], timeout: int = 4) -> Optional[str]:
    """
    Return the first URL among base+paths that responds < 400 AND does not
    redirect back to the homepage (which would mean the path doesn't exist).
    """
    base_norm = base.rstrip("/")
    for path in paths:
        target = base_norm + path
        try:
            r = requests.head(
                target, timeout=timeout, allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if r.status_code >= 400:
                continue
            # Reject if the server silently redirected us back to the root
            final = str(r.url).rstrip("/")
            if final == base_norm or final == base_norm + "/index" or final == base_norm + "/home":
                continue
            return target
        except Exception:
            continue
    return None


def _fetch_activity_for_project(project: dict) -> tuple[int, dict[str, tuple[str, str]]]:
    """
    Discover and fetch up to 3 page types (releases, news, roadmap) for one project.
    Returns (cmc_id, {page_type: (url, text)})
    Thread-safe — creates no shared state.
    """
    cmc_id  = project["cmc_id"]
    base    = (project.get("website") or "").rstrip("/")
    rdm_url = project.get("roadmap_url") or ""

    pages: dict[str, tuple[str, str]] = {}

    if not base:
        return cmc_id, pages

    # Releases / changelog
    rel_url = _probe_first(base, _RELEASES_PATHS)
    if rel_url:
        text = _fetch_text(rel_url)
        if text:
            pages["releases"] = (rel_url, text[:2000])

    # News / blog
    news_url = _probe_first(base, _NEWS_PATHS)
    if news_url:
        text = _fetch_text(news_url)
        if text:
            pages["news"] = (news_url, text[:1500])

    # Roadmap / plans (use the pre-discovered URL from CMC step if available)
    if rdm_url and rdm_url != base:
        # Only fetch if it's not the same as releases/news we already got
        already = {u for u, _ in pages.values()}
        if rdm_url not in already:
            text = _fetch_text(rdm_url)
            if text:
                pages["roadmap"] = (rdm_url, text[:1500])
    else:
        rdm_discovered = _probe_first(base, _ROADMAP_PATHS)
        if rdm_discovered:
            text = _fetch_text(rdm_discovered)
            if text:
                pages["roadmap"] = (rdm_discovered, text[:1500])

    return cmc_id, pages


# ---------------------------------------------------------------------------
# Analyzer class
# ---------------------------------------------------------------------------

class MarketAnalyzer:
    """
    Gemini-powered market analyzer.
    Fully independent — no imports from app.ingestion / app.synthesize / app.brain.
    """

    def __init__(self, mongo_uri: str, mongo_db: str = "kairo"):
        self.mongo_uri = mongo_uri
        self.mongo_db  = mongo_db
        self._gemini   = None
        self._model    = None

    # ------------------------------------------------------------------
    # Gemini client (lazy, independent from NarrativeEngine)
    # ------------------------------------------------------------------

    def _init_gemini(self) -> None:
        if self._gemini:
            return
        from google import genai
        from config.config import Config
        project  = os.getenv("GOOGLE_CLOUD_PROJECT") or Config.GOOGLE_CLOUD_PROJECT
        location = os.getenv("GOOGLE_CLOUD_LOCATION") or Config.GOOGLE_CLOUD_LOCATION
        model    = os.getenv("GEMINI_MODEL")          or Config.GEMINI_MODEL
        if not project:
            raise ValueError("GOOGLE_CLOUD_PROJECT not configured")
        self._gemini = genai.Client(vertexai=True, project=project, location=location)
        self._model  = model
        logger.info("Gemini ready (project=%s, model=%s)", project, model)

    def _call_gemini(self, prompt: str) -> str:
        self._init_gemini()
        response = self._gemini.models.generate_content(
            model=self._model, contents=prompt
        )
        return getattr(response, "text", "") or ""

    # ------------------------------------------------------------------
    # Parallel activity-page fetching
    # ------------------------------------------------------------------

    def _fetch_all_activity_pages(
        self, projects: list[dict], max_workers: int = 10
    ) -> dict[int, dict[str, tuple[str, str]]]:
        """
        Fetch releases / news / roadmap pages for all projects in parallel.
        Returns {cmc_id: {page_type: (url, text)}}
        """
        results: dict[int, dict] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_fetch_activity_for_project, p): p for p in projects}
            for fut in as_completed(futures):
                try:
                    cmc_id, pages = fut.result()
                    results[cmc_id] = pages
                    total = sum(len(t) for _, t in pages.values())
                    logger.debug("pages fetched for id=%s: %s (%d chars)",
                                 cmc_id, list(pages.keys()), total)
                except Exception as exc:
                    proj = futures[fut]
                    logger.warning("page fetch failed for %s: %s", proj.get("symbol"), exc)
                    results[proj["cmc_id"]] = {}
        return results

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_pages_block(
        pages: dict[str, tuple[str, str]], project_name: str
    ) -> str:
        if not pages:
            return _PAGES_NO_CONTENT.format(name=project_name)
        sections = []
        labels = {
            "releases": "RELEASES / CHANGELOG PAGE",
            "news":     "NEWS / BLOG PAGE",
            "roadmap":  "ROADMAP / PLANS PAGE",
        }
        for kind in ("releases", "news", "roadmap"):
            if kind in pages:
                url, text = pages[kind]
                sections.append(
                    f"--- {labels[kind]} ({url}) ---\n{text}\n"
                )
        return _PAGES_WITH_CONTENT.format(sections="\n".join(sections))

    # ------------------------------------------------------------------
    # JSON parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse(raw: str) -> Optional[dict]:
        text = raw.strip()
        if "```" in text:
            for block in text.split("```"):
                block = block.strip().lstrip("json").strip()
                if block.startswith("{"):
                    text = block
                    break
        s = text.find("{")
        e = text.rfind("}") + 1
        if s < 0 or e <= 0:
            return None
        try:
            return json.loads(text[s:e])
        except json.JSONDecodeError:
            return None

    # ------------------------------------------------------------------
    # Per-project analysis
    # ------------------------------------------------------------------

    def _analyze_one(
        self,
        project: dict,
        pages: dict[str, tuple[str, str]],
        fetch_pages: bool,
    ) -> dict:
        name    = project.get("name", "")
        symbol  = project.get("symbol", "")
        rank    = project.get("rank", 0)
        website = project.get("website", "")

        today_month = datetime.now(timezone.utc).strftime("%Y-%m")

        pages_block = (
            self._build_pages_block(pages, name)
            if fetch_pages
            else _PAGES_NO_CONTENT.format(name=name)
        )

        prompt = _PROMPT.format(
            name=name,
            symbol=symbol,
            rank=rank,
            website=website or "(not available)",
            pages_block=pages_block,
            today_month=today_month,
        )

        # Default result (used on error)
        best_url = (
            next((url for url, _ in pages.values()), None)
            or project.get("roadmap_url")
            or website
        )
        result: dict = {
            "cmc_id":               project.get("cmc_id"),
            "symbol":               symbol,
            "name":                 name,
            "display_name":         name,   # overwritten by Gemini if it returns a better name
            "analyzed_at":          datetime.now(timezone.utc).isoformat(),
            "description":          None,
            "ecosystem_category":   None,
            "ecosystem_description": None,
            "trad_fi_equivalent":   None,
            "trad_fi_explanation":  None,
            "latest_release":       None,
            "latest_news_headline": None,
            "activity_summary":     None,
            "activity_source_url":  best_url,
            "activity_source_date": today_month,
            "analysis_confidence":  "low",
            "analysis_error":       None,
            # backward-compat alias consumed by older kairo_data builds
            "roadmap_summary":      None,
            "roadmap_source_url":   best_url,
            "roadmap_source_date":  today_month,
        }

        try:
            raw    = self._call_gemini(prompt)
            parsed = self._parse(raw)
        except Exception as exc:
            logger.error("Gemini failed for %s: %s", name, exc)
            result["analysis_error"] = str(exc)
            return result

        if parsed:
            # For activity_source_url: prefer a Gemini-returned URL that is
            # clearly a sub-page (not just the homepage) over the scraped fallback.
            gemini_url = parsed.get("activity_source_url") or ""
            base_clean = website.rstrip("/")
            # If Gemini returned the bare homepage, keep our scraped URL if better
            if gemini_url and gemini_url.rstrip("/") not in (base_clean, base_clean + "/"):
                final_activity_url = gemini_url
            else:
                final_activity_url = best_url or gemini_url

            result.update({
                "display_name":          parsed.get("display_name") or name,
                "description":           parsed.get("description"),
                "ecosystem_category":    parsed.get("ecosystem_category"),
                "ecosystem_description": parsed.get("ecosystem_description"),
                "trad_fi_equivalent":    parsed.get("trad_fi_equivalent"),
                "trad_fi_explanation":   parsed.get("trad_fi_explanation"),
                "latest_release":        parsed.get("latest_release"),
                "latest_news_headline":  parsed.get("latest_news_headline"),
                "activity_summary":      parsed.get("activity_summary"),
                "activity_source_url":   final_activity_url,
                "activity_source_date":  parsed.get("activity_source_date") or today_month,
                "analysis_confidence":   parsed.get("analysis_confidence", "medium"),
                # alias for backward compat
                "roadmap_summary":       parsed.get("activity_summary"),
                "roadmap_source_url":    final_activity_url,
                "roadmap_source_date":   parsed.get("activity_source_date") or today_month,
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
        fetch_pages: bool = True,
        gemini_delay_s: float = 1.5,
        dry_run: bool = False,
        progress_cb=None,
    ) -> list[dict]:
        """
        Analyze all (or a subset of) top-20 projects.
        progress_cb(current: int, total: int, project_name: str)
        """
        mc  = pymongo.MongoClient(self.mongo_uri, tlsCAFile=__import__('config.config', fromlist=['mongo_tls_ca_file']).mongo_tls_ca_file(), serverSelectionTimeoutMS=2000)
        doc = mc[self.mongo_db][_COLLECTION_CMC].find_one({"_id": _DOC_ID})
        mc.close()

        if not doc or not doc.get("projects"):
            raise ValueError(
                f"No market data in {self.mongo_db}.{_COLLECTION_CMC}. "
                "Run 'python -m app.ingestion.crypto_markets' first."
            )

        projects = doc["projects"]
        if symbols:
            upper = {s.upper() for s in symbols}
            projects = [p for p in projects if p.get("symbol", "").upper() in upper]

        total = len(projects)
        logger.info("Starting analysis of %d project(s)…", total)

        # Phase 1: fetch all activity pages in parallel
        all_pages: dict[int, dict] = {}
        if fetch_pages:
            logger.info("Phase 1: fetching releases/news/roadmap pages in parallel…")
            all_pages = self._fetch_all_activity_pages(projects)
            fetched = sum(1 for p in all_pages.values() if p)
            logger.info("Phase 1 done: %d/%d projects had fetchable pages", fetched, total)

        # Phase 2: sequential Gemini calls
        results: list[dict] = []
        for i, project in enumerate(projects):
            name  = project.get("name", project.get("symbol", "?"))
            pages = all_pages.get(project.get("cmc_id", -1), {})
            logger.info("[%d/%d] Gemini: %s (%d page types)", i + 1, total, name, len(pages))

            analysis = self._analyze_one(project, pages, fetch_pages)
            results.append(analysis)

            if progress_cb:
                progress_cb(i + 1, total, name)

            if i < total - 1:
                time.sleep(gemini_delay_s)

        if not dry_run:
            self._save(results)

        return results

    def _save(self, results: list[dict]) -> None:
        mc = pymongo.MongoClient(self.mongo_uri, tlsCAFile=__import__('config.config', fromlist=['mongo_tls_ca_file']).mongo_tls_ca_file(), serverSelectionTimeoutMS=2000)
        mc[self.mongo_db][_COLLECTION_ANALYSIS].update_one(
            {"_id": _DOC_ID},
            {"$set": {"analyzed_at": datetime.now(timezone.utc), "projects": results}},
            upsert=True,
        )
        mc.close()
        logger.info("Saved %d analyses to %s.%s", len(results), self.mongo_db, _COLLECTION_ANALYSIS)

    @staticmethod
    def load_from_mongo(mongo_uri: str, mongo_db: str = "kairo") -> Optional[dict]:
        """Return the analysis document from MongoDB, or None."""
        try:
            mc  = pymongo.MongoClient(mongo_uri, tlsCAFile=__import__('config.config', fromlist=['mongo_tls_ca_file']).mongo_tls_ca_file(), serverSelectionTimeoutMS=2000)
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
    load_dotenv(override=True)
    from config.config import Config

    dry_run   = "--dry"  in sys.argv
    fast_mode = "--fast" in sys.argv
    symbols   = [a.upper() for a in sys.argv[1:] if not a.startswith("--")]

    mongo_uri = os.getenv("MONGO_URI") or Config.MONGO_URI
    mongo_db  = os.getenv("MONGO_DB")  or Config.MONGO_DB or "kairo"
    if not mongo_uri:
        print("ERROR: MONGO_URI not configured"); sys.exit(1)

    analyzer = MarketAnalyzer(mongo_uri, mongo_db)

    results = analyzer.analyze_all(
        symbols=symbols or None,
        fetch_pages=not fast_mode,
        dry_run=dry_run,
        progress_cb=lambda c, t, n: print(f"  [{c:>2}/{t}] ✓ {n}"),
    )

    print(f"\n{'Sym':<8}  {'Ecosystem':<14}  {'TradFi':<22}  {'Release':<20}  Conf")
    print("─" * 80)
    for r in results:
        err  = "❌ " if r.get("analysis_error") else "   "
        eco  = (r.get("ecosystem_category") or "—")[:13]
        trad = (r.get("trad_fi_equivalent") or "—")[:21]
        rel  = (r.get("latest_release") or "—")[:19]
        conf = r.get("analysis_confidence") or "—"
        print(f"{err}{r.get('symbol','?'):<8}  {eco:<14}  {trad:<22}  {rel:<20}  {conf}")

    if not dry_run:
        print(f"\nSaved → {mongo_db}.{_COLLECTION_ANALYSIS}")


if __name__ == "__main__":
    _cli_main()
