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

_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
_PROMPT     = (_PROMPT_DIR / "regulation_analyzer_prompt.txt").read_text(encoding="utf-8")


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

        prompt = _PROMPT.replace("{known_ids}", known_ids_text)

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
