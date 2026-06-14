"""
Concept Tracker: Fetches and stores digital currency concept explanations via Gemini.

Each concept is stored once, keyed by concept_slug (e.g. "blockchain", "cryptocurrency").
The unique index on concept_slug guarantees idempotency — submitting the same concept twice
leaves the collection unchanged.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.server_api import ServerApi

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "concept_explainer_prompt.txt"
_PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")


def _fetch_url_content(url: str, max_chars: int = 4000) -> str:
    """Fetch plain text content from a URL. Returns empty string on failure."""
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KairoBot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        # Strip HTML tags
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception as exc:
        logger.warning("[CONCEPTTRAK] URL fetch failed for %s: %s", url, exc)
        return ""


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _serialize_doc(doc: dict) -> dict:
    return {
        k: (v.isoformat() if isinstance(v, datetime) else v)
        for k, v in doc.items()
        if k != "_id"
    }


class ConceptTracker:
    COLLECTION = "crypto_concepts"

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
            col = self.db[self.COLLECTION]
            col.create_index([("concept_slug", ASCENDING)], unique=True, background=True)
            col.create_index([("added_at", DESCENDING)], background=True)
        except Exception as exc:
            logger.warning("[CONCEPTTRAK] Index creation warning: %s", exc)

    # ------------------------------------------------------------------
    # Gemini fetch & store
    # ------------------------------------------------------------------

    def fetch_and_store(
        self, gemini_engine, concept_name: str, source_url: str
    ) -> dict:
        """
        Fetch URL content, call Gemini to explain the concept, store in MongoDB.
        Returns a result dict with keys: saved, skipped, error (optional), concept.
        """
        slug = _slugify(concept_name)
        existing_slugs = self._get_known_slugs()

        if slug in existing_slugs:
            logger.info("[CONCEPTTRAK] Concept '%s' already known — skipping", slug)
            return {"saved": 0, "skipped": 1, "slug": slug}

        url_content = _fetch_url_content(source_url)
        existing_list = (
            "\n".join(f"  - {s}" for s in sorted(existing_slugs))
            or "  (none yet)"
        )

        prompt = (
            _PROMPT_TEMPLATE
            .replace("{concept_name}", concept_name)
            .replace("{source_url}", source_url)
            .replace("{url_content}", url_content or "(content unavailable)")
            .replace("{existing_concepts}", existing_list)
        )

        logger.info("[CONCEPTTRAK] Calling Gemini for concept '%s'", concept_name)
        added_at = datetime.now(timezone.utc)

        try:
            response = gemini_engine._call_gemini_with_backoff(prompt)
            raw_text = response.text.strip()
        except Exception as exc:
            logger.exception("[CONCEPTTRAK] Gemini call failed")
            return {"error": str(exc), "saved": 0, "skipped": 0}

        parsed = self._parse_response(raw_text)
        if "error" in parsed:
            return {**parsed, "saved": 0, "skipped": 0}

        if parsed.get("is_duplicate"):
            return {"saved": 0, "skipped": 1, "slug": parsed.get("concept_slug", slug)}

        doc = {
            **parsed,
            "concept_slug": parsed.get("concept_slug") or slug,
            "added_at": added_at,
        }
        doc.pop("is_duplicate", None)

        try:
            self.db[self.COLLECTION].update_one(
                {"concept_slug": doc["concept_slug"]},
                {"$setOnInsert": doc},
                upsert=True,
            )
            logger.info("[CONCEPTTRAK] Saved concept '%s'", doc["concept_slug"])
            return {"saved": 1, "skipped": 0, "slug": doc["concept_slug"], "concept": doc}
        except Exception as exc:
            logger.warning("[CONCEPTTRAK] Failed to upsert '%s': %s", doc.get("concept_slug"), exc)
            return {"error": str(exc), "saved": 0, "skipped": 0}

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_all_concepts(self) -> list[dict]:
        try:
            docs = list(
                self.db[self.COLLECTION]
                .find({}, {"_id": 0})
                .sort([("added_at", DESCENDING)])
            )
            return [_serialize_doc(d) for d in docs]
        except Exception as exc:
            logger.warning("[CONCEPTTRAK] get_all_concepts failed: %s", exc)
            return []

    def purge_all(self) -> int:
        try:
            result = self.db[self.COLLECTION].delete_many({})
            return result.deleted_count
        except Exception as exc:
            logger.warning("[CONCEPTTRAK] purge_all failed: %s", exc)
            return 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_known_slugs(self) -> set[str]:
        try:
            docs = self.db[self.COLLECTION].find({}, {"concept_slug": 1, "_id": 0})
            return {d["concept_slug"] for d in docs if d.get("concept_slug")}
        except Exception as exc:
            logger.warning("[CONCEPTTRAK] _get_known_slugs failed: %s", exc)
            return set()

    def _parse_response(self, raw: str) -> dict:
        text = raw
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
            logger.error("[CONCEPTTRAK] JSON parse failed: %s | raw: %s", exc, raw[:400])
            return {"error": f"JSON parse failed: {exc}"}
