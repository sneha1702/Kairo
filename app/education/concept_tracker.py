"""
Concept Tracker: Fetches digital currency concept explanations via Gemini from a URL.

Gemini auto-discovers ALL concepts on the page and provides grouping (anchor → related).
Each concept is stored once, keyed by concept_slug — fully idempotent.
Groups are upserted per anchor, merging related slugs across multiple fetches.
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

COLLECTION_CONCEPTS = "crypto_concepts"
COLLECTION_GROUPS   = "crypto_concept_groups"


def _fetch_url_content(url: str, max_chars: int = 5000) -> str:
    """Fetch and strip HTML from a URL. Returns empty string on failure."""
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; KairoBot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception as exc:
        logger.warning("[CONCEPTTRAK] URL fetch failed for %s: %s", url, exc)
        return ""


def _serialize_doc(doc: dict) -> dict:
    return {
        k: (v.isoformat() if isinstance(v, datetime) else v)
        for k, v in doc.items()
        if k != "_id"
    }


class ConceptTracker:

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
            self.db[COLLECTION_CONCEPTS].create_index(
                [("concept_slug", ASCENDING)], unique=True, background=True
            )
            self.db[COLLECTION_CONCEPTS].create_index(
                [("added_at", DESCENDING)], background=True
            )
            self.db[COLLECTION_GROUPS].create_index(
                [("anchor_slug", ASCENDING)], unique=True, background=True
            )
        except Exception as exc:
            logger.warning("[CONCEPTTRAK] Index creation warning: %s", exc)

    # ------------------------------------------------------------------
    # Main public method: fetch URL → Gemini → store concepts + groups
    # ------------------------------------------------------------------

    def fetch_and_store_from_url(self, gemini_engine, source_url: str) -> dict:
        """
        Fetch URL content, call Gemini to auto-discover ALL concepts and their grouping,
        store new concepts and upsert group relationships.
        Returns: {saved, skipped, total_found, groups_updated, error (optional)}
        """
        existing_slugs = self._get_known_slugs()
        url_content = _fetch_url_content(source_url)

        existing_list = (
            "\n".join(f"  - {s}" for s in sorted(existing_slugs))
            or "  (none yet)"
        )

        prompt = (
            _PROMPT_TEMPLATE
            .replace("{source_url}", source_url)
            .replace("{url_content}", url_content or "(page content unavailable)")
            .replace("{existing_concepts}", existing_list)
        )

        logger.info("[CONCEPTTRAK] Calling Gemini for URL: %s", source_url)
        added_at = datetime.now(timezone.utc)

        try:
            response = gemini_engine._call_gemini_with_backoff(prompt)
            raw_text = response.text.strip()
        except Exception as exc:
            logger.exception("[CONCEPTTRAK] Gemini call failed")
            return {"error": str(exc), "saved": 0, "skipped": 0, "total_found": 0}

        parsed = self._parse_response(raw_text)
        if "error" in parsed:
            return {**parsed, "saved": 0, "skipped": 0, "total_found": 0}

        concepts = parsed.get("concepts", [])
        groups   = parsed.get("groups", [])
        source_title = parsed.get("source_title", "")

        saved, skipped = self._upsert_concepts(concepts, existing_slugs, source_url, source_title, added_at)
        groups_updated = self._upsert_groups(groups, added_at)

        logger.info(
            "[CONCEPTTRAK] Done — saved=%d skipped=%d groups=%d", saved, skipped, groups_updated
        )
        return {
            "saved":          saved,
            "skipped":        skipped,
            "total_found":    len(concepts),
            "groups_updated": groups_updated,
        }

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_all_concepts(self) -> list[dict]:
        try:
            docs = list(
                self.db[COLLECTION_CONCEPTS]
                .find({}, {"_id": 0})
                .sort([("added_at", DESCENDING)])
            )
            return [_serialize_doc(d) for d in docs]
        except Exception as exc:
            logger.warning("[CONCEPTTRAK] get_all_concepts failed: %s", exc)
            return []

    def get_all_groups(self) -> list[dict]:
        try:
            docs = list(self.db[COLLECTION_GROUPS].find({}, {"_id": 0}))
            return [_serialize_doc(d) for d in docs]
        except Exception as exc:
            logger.warning("[CONCEPTTRAK] get_all_groups failed: %s", exc)
            return []

    def purge_all(self) -> int:
        total = 0
        try:
            total += self.db[COLLECTION_CONCEPTS].delete_many({}).deleted_count
            self.db[COLLECTION_GROUPS].delete_many({})
        except Exception as exc:
            logger.warning("[CONCEPTTRAK] purge_all failed: %s", exc)
        return total

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_known_slugs(self) -> set[str]:
        try:
            docs = self.db[COLLECTION_CONCEPTS].find({}, {"concept_slug": 1, "_id": 0})
            return {d["concept_slug"] for d in docs if d.get("concept_slug")}
        except Exception as exc:
            logger.warning("[CONCEPTTRAK] _get_known_slugs failed: %s", exc)
            return set()

    def _upsert_concepts(
        self,
        concepts: list[dict],
        known_slugs: set[str],
        source_url: str,
        source_title: str,
        added_at: datetime,
    ) -> tuple[int, int]:
        saved = skipped = 0
        for c in concepts:
            slug = (c.get("concept_slug") or "").strip()
            if not slug:
                skipped += 1
                continue
            if slug in known_slugs:
                skipped += 1
                continue
            doc = {
                **c,
                "concept_slug": slug,
                "source_url":   c.get("source_url") or source_url,
                "source_title": c.get("source_title") or source_title,
                "added_at":     added_at,
            }
            try:
                self.db[COLLECTION_CONCEPTS].update_one(
                    {"concept_slug": slug},
                    {"$setOnInsert": doc},
                    upsert=True,
                )
                known_slugs.add(slug)
                saved += 1
            except Exception as exc:
                logger.warning("[CONCEPTTRAK] Failed to upsert '%s': %s", slug, exc)
                skipped += 1
        return saved, skipped

    def _upsert_groups(self, groups: list[dict], updated_at: datetime) -> int:
        count = 0
        for g in groups:
            anchor  = (g.get("anchor_slug") or "").strip()
            related = [s for s in (g.get("related_slugs") or []) if s]
            if not anchor:
                continue
            try:
                self.db[COLLECTION_GROUPS].update_one(
                    {"anchor_slug": anchor},
                    {
                        "$set":       {"updated_at": updated_at},
                        "$addToSet":  {"related_slugs": {"$each": related}},
                        "$setOnInsert": {"anchor_slug": anchor},
                    },
                    upsert=True,
                )
                count += 1
            except Exception as exc:
                logger.warning("[CONCEPTTRAK] Failed to upsert group '%s': %s", anchor, exc)
        return count

    def _parse_response(self, raw: str) -> dict:
        text = raw
        if "```" in text:
            start = text.find("```")
            end   = text.rfind("```")
            text  = text[start:end]
            text  = text[text.find("\n") + 1:]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("[CONCEPTTRAK] JSON parse failed: %s | raw: %s", exc, raw[:500])
            return {"error": f"JSON parse failed: {exc}"}
