"""
Regulation Tracker: Fetches crypto regulatory developments via Gemini and stores them in MongoDB.

Storage strategy — time-series with dedup:
  Each regulation is stored once, keyed by publication date (event_datetime).
  The `id` field (JURISDICTION-YYYYMMDD-slug) carries a unique index — fetching the
  same regulation twice leaves the collection unchanged ($setOnInsert upsert).
  All regulation documents carry an `event_datetime` datetime field (parsed from
  date_of_event) which is indexed for efficient time-range queries.

Time-series queries available:
  get_regulations_by_daterange(start, end)  — slice by publication date
  get_timeline_summary(lookback_days)       — aggregate counts by month/jurisdiction
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.server_api import ServerApi

logger = logging.getLogger(__name__)

_SCHEMA_PATH = Path(__file__).resolve().parent / "crypto_regulation_schema.json"

_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
_PROMPT     = (_PROMPT_DIR / "regulation_analyzer_prompt.txt").read_text(encoding="utf-8")


def _parse_event_date(date_str: str) -> Optional[datetime]:
    """Parse a YYYY-MM-DD string into a UTC midnight datetime, or None on failure."""
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _serialize_doc(doc: dict) -> dict:
    """Convert all datetime values in a MongoDB document to ISO strings for JSON output."""
    return {
        k: (v.isoformat() if isinstance(v, datetime) else v)
        for k, v in doc.items()
    }


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
            regs = self.db[self.COLLECTION_REGS]
            # Dedup guarantee — one document per regulation id, ever
            regs.create_index([("id", ASCENDING)], unique=True, background=True)
            # Primary time-series axis — publication date as a real datetime
            regs.create_index([("event_datetime", DESCENDING)], background=True)
            # Compound index for filtered time-series queries (date + jurisdiction)
            regs.create_index(
                [("event_datetime", DESCENDING), ("jurisdiction_code", ASCENDING)],
                background=True,
            )
            # Supporting index for significance-filtered queries
            regs.create_index(
                [("event_datetime", DESCENDING), ("classification.significance", ASCENDING)],
                background=True,
            )
            self.db[self.COLLECTION_RUNS].create_index(
                [("run_at", DESCENDING)], background=True
            )
        except Exception as exc:
            logger.warning("[REGTRAK] Index creation warning: %s", exc)

    # ------------------------------------------------------------------
    # Gemini fetch & store
    # ------------------------------------------------------------------

    def fetch_and_store(self, gemini_engine) -> dict:
        """
        Call Gemini with the regulations prompt, parse the JSON response,
        deduplicate against existing MongoDB records, save only new ones.
        Returns a summary dict with saved/skipped counts.

        Idempotency: the unique index on `id` combined with $setOnInsert means
        running this twice on the same data makes zero additional writes.
        """
        known_ids = self._get_known_ids()
        known_ids_text = (
            "\n".join(f"  - {id_}" for id_ in sorted(known_ids))
            or "  (none yet — this is the first run)"
        )

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
        metadata    = parsed.get("metadata", {})

        saved, skipped = self._upsert_regulations(regulations, known_ids, run_at)

        run_doc = {
            "run_at":             run_at,
            "regulations_found":  len(regulations),
            "saved":              saved,
            "skipped":            skipped,
            "sources_checked":    metadata.get("sources_checked", []),
            "coverage_gaps":      parsed.get("coverage_gaps", []),
            "unverified_stories": parsed.get("unverified_stories", []),
            "prompt_version":     metadata.get("prompt_version", "v3"),
        }
        try:
            self.db[self.COLLECTION_RUNS].insert_one(run_doc)
        except Exception as exc:
            logger.warning("[REGTRAK] Failed to save run metadata: %s", exc)

        logger.info("[REGTRAK] Run complete — saved=%d skipped=%d", saved, skipped)
        return {
            "saved":       saved,
            "skipped":     skipped,
            "total_found": len(regulations),
            "run_at":      run_at.isoformat(),
        }

    # ------------------------------------------------------------------
    # Time-series read helpers
    # ------------------------------------------------------------------

    def get_latest_regulations(self, limit: int = 60) -> list[dict]:
        """Return the most recent regulations sorted by publication date descending."""
        try:
            docs = list(
                self.db[self.COLLECTION_REGS]
                .find({}, {"_id": 0})
                .sort([("event_datetime", DESCENDING)])
                .limit(limit)
            )
            return [_serialize_doc(d) for d in docs]
        except Exception as exc:
            logger.warning("[REGTRAK] get_latest_regulations failed: %s", exc)
            return []

    def get_regulations_by_daterange(
        self,
        start: datetime,
        end: datetime,
        jurisdiction_code: Optional[str] = None,
        significance: Optional[str] = None,
    ) -> list[dict]:
        """
        Return all regulations whose publication date falls within [start, end].
        Optionally filter by jurisdiction_code (e.g. 'US', 'EU') and/or significance.
        Both start and end must be timezone-aware datetimes.
        """
        query: dict = {"event_datetime": {"$gte": start, "$lte": end}}
        if jurisdiction_code:
            query["jurisdiction_code"] = jurisdiction_code
        if significance:
            query["classification.significance"] = significance
        try:
            docs = list(
                self.db[self.COLLECTION_REGS]
                .find(query, {"_id": 0})
                .sort([("event_datetime", DESCENDING)])
            )
            return [_serialize_doc(d) for d in docs]
        except Exception as exc:
            logger.warning("[REGTRAK] get_regulations_by_daterange failed: %s", exc)
            return []

    def get_timeline_summary(self, lookback_days: int = 180) -> list[dict]:
        """
        Aggregate regulation counts by month and jurisdiction for the past
        `lookback_days`. Returns a list of {year, month, jurisdiction_code, count}
        dicts sorted by date ascending — suitable for charting a time-series trend.
        """
        since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        pipeline = [
            {"$match": {"event_datetime": {"$gte": since}}},
            {"$group": {
                "_id": {
                    "year":              {"$year":  "$event_datetime"},
                    "month":             {"$month": "$event_datetime"},
                    "jurisdiction_code": "$jurisdiction_code",
                },
                "count":             {"$sum": 1},
                "high_significance": {"$sum": {
                    "$cond": [{"$eq": ["$classification.significance", "high"]}, 1, 0]
                }},
            }},
            {"$sort": {"_id.year": 1, "_id.month": 1}},
            {"$project": {
                "_id":               0,
                "year":              "$_id.year",
                "month":             "$_id.month",
                "jurisdiction_code": "$_id.jurisdiction_code",
                "count":             1,
                "high_significance": 1,
            }},
        ]
        try:
            return list(self.db[self.COLLECTION_REGS].aggregate(pipeline))
        except Exception as exc:
            logger.warning("[REGTRAK] get_timeline_summary failed: %s", exc)
            return []

    def get_last_run(self) -> Optional[dict]:
        """Return metadata from the most recent fetch run."""
        try:
            doc = self.db[self.COLLECTION_RUNS].find_one(
                {}, {"_id": 0}, sort=[("run_at", DESCENDING)]
            )
            return _serialize_doc(doc) if doc else None
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
                # Already in MongoDB — $setOnInsert would also be a no-op, but skip
                # early to avoid the round-trip.
                skipped += 1
                continue

            # Parse the publication date string into a real datetime for time-series indexing.
            event_dt = _parse_event_date(reg.get("date_of_event", ""))

            doc = {
                **reg,
                "event_datetime": event_dt or run_at,  # fall back to now if unparseable
                "stored_at":      run_at,
            }
            try:
                # $setOnInsert: if the id already exists the document is untouched.
                # The unique index on `id` provides an additional DB-level guarantee.
                self.db[self.COLLECTION_REGS].update_one(
                    {"id": reg_id},
                    {"$setOnInsert": doc},
                    upsert=True,
                )
                known_ids.add(reg_id)
                saved += 1
            except Exception as exc:
                logger.warning("[REGTRAK] Failed to upsert %s: %s", reg_id, exc)
                skipped += 1
        return saved, skipped
