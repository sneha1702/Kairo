"""
Regulation Tracker: Fetches crypto regulatory developments via Gemini and stores them in MongoDB.

Dedup strategy:
  Each regulation has a stable `id` field (JURISDICTION-YYYYMMDD-slug).
  On each run, existing IDs are passed to Gemini so it knows what we already have.
  After the response, only regulations with new IDs are stored.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.server_api import ServerApi

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent / "crypto_regulation_schema.json"

_PROMPT_DIR         = Path(__file__).resolve().parents[1] / "prompts"
_PROMPT             = (_PROMPT_DIR / "regulation_analyzer_prompt.txt").read_text(encoding="utf-8")

REGULATION_PROMPT = """
You are a crypto regulatory intelligence analyst. Your job is to find, read, and summarise the latest regulatory developments in cryptocurrency from around the world, with particular emphasis on China, India, the European Union, and the United States.

SOURCE HIERARCHY (strictly enforced)

Tier 1 — Law firm policy trackers (cite official documents, written by lawyers). Fetch and read these first:
- https://www.lw.com/en/us-crypto-policy-tracker/regulatory-developments
- https://www.lw.com/en/markets-in-crypto-assets-regulation-tracker (EU focus)
- https://www.paulhastings.com/insights/crypto-policy-tracker
- https://www.trmlabs.com/reports-and-whitepapers/global-crypto-policy-review-outlook-2025-26
- China/Asia: Han Kun Law Offices, Norton Rose Fulbright, or CMS Expert Guides on China crypto regulation
- India: AZB & Partners, or other Tier 1 Indian law firm updates on VDA/FIU/SEBI/RBI

Tier 2 — Official regulator feeds (ground truth):
- US: https://www.sec.gov/news/pressreleases, https://www.cftc.gov/PressRoom/PressReleases
- EU: https://www.esma.europa.eu/press-news/esma-news (MiCA focus)
- UK: https://www.fca.org.uk/news/press-releases
- China: People's Bank of China (PBoC) notices (pbc.gov.cn), CSRC announcements (csrc.gov.cn)
- India: https://www.rbi.org.in/, https://www.sebi.gov.in/, https://fiuindia.gov.in/
- Singapore: https://www.mas.gov.sg/news
- FATF: https://www.fatf-gafi.org/en/publications.html
- BIS: https://www.bis.org/press/index.htm

Tier 3 — Specialist crypto journalism (use to catch stories missed above, only if article links to primary source):
- https://cryptonews.com/news/regulation-news/
- https://www.theblock.co/category/policy
- https://decrypt.co/category/crypto-biz (regulatory stories only)

REJECTED sources — Do not use: CoinDesk editorial opinion, Twitter/X threads without primary source links, anonymous blog posts.

RESEARCH STEPS:
Step 1 — Fetch Tier 1 sources. Extract every regulatory development published or updated within the last 30 days. For each: note exact publication date, jurisdiction, regulator, and specific law/rule/guidance name. Pay special attention to China's evolving stance on RWAs/stablecoins vs. general crypto ban, India's VDA/FIU/SEBI developments, EU MiCA implementation, and US CFTC/SEC/banking updates.
Step 2 — Verify with Tier 2 where possible. For every development found in Step 1, attempt to find the original regulator press release or official document. If not found, mark "official_source_verified": false.
Step 3 — Catch recent stories from Tier 3 only if not already captured.
Step 4 — Score and classify each development.

ALREADY KNOWN REGULATION IDs (skip these, they are already stored — DO NOT re-report them):
{known_ids}

OUTPUT FORMAT — return ONLY valid JSON (no markdown fences, no explanation) matching this schema exactly:

{{
  "metadata": {{
    "generated_at": "<ISO 8601 datetime>",
    "lookback_days": 30,
    "sources_checked": ["<url1>", "<url2>"],
    "prompt_version": "v2"
  }},
  "regulations": [
    {{
      "id": "<JURISDICTION_CODE>-<YYYYMMDD>-<short-slug>",
      "jurisdiction": "<country or bloc name>",
      "jurisdiction_code": "<ISO 3166-1 alpha-2 or bloc code e.g. US, EU, UK, SG, IN, CN>",
      "regulator": "<name of regulating body>",
      "regulation_name": "<official name of rule/law/guidance>",
      "event_type": "<one of: law_passed|rule_published|guidance_issued|enforcement_action|deadline|consultation_opened|consultation_closed>",
      "date_of_event": "<YYYY-MM-DD>",
      "date_captured": "<YYYY-MM-DD today>",
      "source_tier": "<1|2|3>",
      "source_url": "<url>",
      "official_source_url": "<url or null>",
      "official_source_verified": <true|false>,
      "summary": "<plain English, max 100 words, no jargon>",
      "classification": {{
        "impact_direction": "<restrictive|permissive|neutral|mixed>",
        "market_access": "<improves|restricts|no_change>",
        "beneficiary": ["<retail_investors|institutional_investors|exchanges|defi_protocols|stablecoin_issuers|asset_managers|banks|no_clear_beneficiary>"],
        "harm_vector": ["<retail_investors|exchanges|defi_protocols|stablecoin_issuers|privacy|innovation|none>"],
        "theme": ["<market_access|consumer_protection|security_of_assets|aml_kyc|tax_reporting|stablecoin_rules|defi_regulation|tokenisation|cbdc|enforcement|licensing|self_custody>"],
        "status": "<proposed|passed|effective|deadline_approaching|enforcement_action>",
        "significance": "<high|medium|low>"
      }},
      "key_dates": {{
        "proposed": "<YYYY-MM-DD or null>",
        "passed": "<YYYY-MM-DD or null>",
        "effective": "<YYYY-MM-DD or null>",
        "deadline": "<YYYY-MM-DD or null>"
      }},
      "flagged_contradictions": "<string or null>"
    }}
  ],
  "unverified_stories": [
    {{
      "headline": "<headline>",
      "source": "<url>",
      "reason_excluded": "<reason>"
    }}
  ],
  "coverage_gaps": ["<gap description>"]
}}

QUALITY RULES:
- Return at least 5 and at most 15 regulations per run
- Prioritise balance across China, India, EU, US
- Explicitly flag major shifts (e.g. China RWA tokenization vs. crypto ban enforcement)
- For India: track FIU-IND registrations, AML updates, SEBI/RBI coordination
- Only include regulations from the last 30 days
- Be conservative — if unsure, mark official_source_verified as false
- Summaries must be plain English, max 100 words, no legal jargon
"""


class RegulationTracker:
    COLLECTION_REGS = "crypto_regulations"
    COLLECTION_RUNS = "regulation_runs"

    def __init__(self, mongo_uri: str, db_name: str = "kairo"):
        from config.config import mongo_tls_ca_file
        self.client = MongoClient(
            mongo_uri,
            tlsCAFile=mongo_tls_ca_file(),
            server_api=ServerApi("1"),
            connect=False,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
        )
        self.db = self.client[db_name]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        try:
            self.db[self.COLLECTION_REGS].create_index(
                [("id", ASCENDING)], unique=True, background=True
            )
            self.db[self.COLLECTION_REGS].create_index(
                [("date_of_event", DESCENDING)], background=True
            )
            self.db[self.COLLECTION_REGS].create_index(
                [("jurisdiction_code", ASCENDING)], background=True
            )
            self.db[self.COLLECTION_RUNS].create_index(
                [("run_at", DESCENDING)], background=True
            )
        except Exception as exc:
            logger.warning("[REGTRAK] Index creation warning: %s", exc)

    # ------------------------------------------------------------------
    # Gemini fetch
    # ------------------------------------------------------------------

    def fetch_and_store(self, gemini_engine) -> dict:
        """
        Call Gemini with the regulations prompt, parse the JSON response,
        deduplicate against existing MongoDB records, save only new ones.
        Returns a summary dict with saved/skipped counts.
        """
        known_ids = self._get_known_ids()
        known_ids_text = "\n".join(f"  - {id_}" for id_ in sorted(known_ids)) or "  (none yet — this is the first run)"

        prompt = REGULATION_PROMPT.format(known_ids=known_ids_text)

        logger.info("[REGTRAK] Calling Gemini for regulation update (known IDs: %d)", len(known_ids))
        run_at = datetime.now(timezone.utc)

        try:
            response = gemini_engine._call_gemini_with_backoff(prompt)
            raw_text = response.text.strip()
        except Exception as exc:
            logger.exception("[REGTRAK] Gemini call failed")
            return {"error": str(exc), "saved": 0, "skipped": 0, "run_at": run_at.isoformat()}

        parsed = self._parse_gemini_response(raw_text)
        if "error" in parsed:
            return {**parsed, "saved": 0, "skipped": 0, "run_at": run_at.isoformat()}

        regulations = parsed.get("regulations", [])
        metadata = parsed.get("metadata", {})
        metadata["generated_at"] = run_at.isoformat()

        saved, skipped = self._upsert_regulations(regulations, known_ids, run_at)

        run_doc = {
            "run_at": run_at,
            "regulations_found": len(regulations),
            "saved": saved,
            "skipped": skipped,
            "sources_checked": metadata.get("sources_checked", []),
            "coverage_gaps": parsed.get("coverage_gaps", []),
            "unverified_stories": parsed.get("unverified_stories", []),
            "prompt_version": metadata.get("prompt_version", "v2"),
        }
        try:
            self.db[self.COLLECTION_RUNS].insert_one(run_doc)
        except Exception as exc:
            logger.warning("[REGTRAK] Failed to save run metadata: %s", exc)

        logger.info("[REGTRAK] Run complete — saved=%d skipped=%d", saved, skipped)
        return {
            "saved": saved,
            "skipped": skipped,
            "total_found": len(regulations),
            "run_at": run_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_latest_regulations(self, limit: int = 50) -> list[dict]:
        """Return the most recent regulations, newest event first."""
        try:
            docs = list(
                self.db[self.COLLECTION_REGS]
                .find({}, {"_id": 0})
                .sort([("stored_at", DESCENDING)])
                .limit(limit)
            )
            for doc in docs:
                for k, v in doc.items():
                    if isinstance(v, datetime):
                        doc[k] = v.isoformat()
            return docs
        except Exception as exc:
            logger.warning("[REGTRAK] get_latest_regulations failed: %s", exc)
            return []

    def get_last_run(self) -> Optional[dict]:
        """Return metadata from the most recent fetch run."""
        try:
            doc = self.db[self.COLLECTION_RUNS].find_one(
                {}, {"_id": 0}, sort=[("run_at", DESCENDING)]
            )
            if doc:
                for k, v in doc.items():
                    if isinstance(v, datetime):
                        doc[k] = v.isoformat()
            return doc
        except Exception as exc:
            logger.warning("[REGTRAK] get_last_run failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_known_ids(self) -> set[str]:
        try:
            docs = self.db[self.COLLECTION_REGS].find({}, {"id": 1, "_id": 0})
            return {d["id"] for d in docs if d.get("id")}
        except Exception as exc:
            logger.warning("[REGTRAK] _get_known_ids failed: %s", exc)
            return set()

    def _parse_gemini_response(self, raw: str) -> dict:
        text = raw
        # Strip markdown fences if Gemini wrapped the JSON
        if "```" in text:
            start = text.find("```")
            end = text.rfind("```")
            text = text[start:end]
            text = text[text.find("\n") + 1:]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("[REGTRAK] JSON parse failed: %s | raw (first 500): %s", exc, raw[:500])
            return {"error": f"JSON parse failed: {exc}"}

    def _upsert_regulations(
        self, regulations: list[dict], known_ids: set[str], run_at: datetime
    ) -> tuple[int, int]:
        saved = skipped = 0
        for reg in regulations:
            reg_id = (reg.get("id") or "").strip()
            if not reg_id:
                logger.warning("[REGTRAK] Regulation missing id — skipping")
                skipped += 1
                continue
            if reg_id in known_ids:
                skipped += 1
                continue
            doc = {**reg, "stored_at": run_at}
            try:
                self.db[self.COLLECTION_REGS].update_one(
                    {"id": reg_id}, {"$setOnInsert": doc}, upsert=True
                )
                known_ids.add(reg_id)
                saved += 1
            except Exception as exc:
                logger.warning("[REGTRAK] Failed to upsert %s: %s", reg_id, exc)
                skipped += 1
        return saved, skipped
