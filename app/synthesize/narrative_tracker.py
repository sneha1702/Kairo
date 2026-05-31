"""
Narrative Tracker: Persists and retrieves narratives over time.
Uses MongoDB for current narrative state and a time series collection for history.

Deduplication strategy:
  Each narrative is identified by a stable (narrative_id, user_id) pair.
  Gemini is instructed to reuse known narrative_ids for the same theme.
  Fallback: if Gemini omits narrative_id, one is generated from the name.
  Upsert key: narrative_id + user_id  →  one doc per theme per user.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import CollectionInvalid, OperationFailure

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stable ID helpers
# ---------------------------------------------------------------------------

def make_narrative_id(narrative: Dict[str, Any]) -> str:
    """
    Return a stable snake_case narrative_id.
    Prefers an id supplied by Gemini; generates one from name as fallback.
    """
    nid = (narrative.get("narrative_id") or "").strip()
    if nid and re.match(r'^[a-z][a-z0-9_]{2,59}$', nid):
        return nid
    # Generate from name
    name = narrative.get("name") or "unknown_narrative"
    generated = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    return generated[:60] or "unknown_narrative"


# ---------------------------------------------------------------------------
# NarrativeTracker
# ---------------------------------------------------------------------------

class NarrativeTracker:
    def __init__(self, mongo_uri: str, db_name: str = "kairo"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self._ensure_collections()

    def _ensure_collections(self) -> None:
        existing = set(self.db.list_collection_names())

        # ── narratives (current state, one doc per narrative_id+user_id) ───────
        if "narratives" not in existing:
            self.db.create_collection("narratives")
            logger.info("Created MongoDB collection: narratives")

        # Drop legacy name-unique index if it exists, create correct one
        try:
            idx_info = self.db.narratives.index_information()
            for idx_name, idx_def in idx_info.items():
                keys = [k for k, _ in idx_def.get("key", [])]
                # Drop old single-field name index
                if keys == ["name"] and idx_def.get("unique"):
                    self.db.narratives.drop_index(idx_name)
                    logger.info("Dropped legacy name-unique index")
        except Exception as exc:
            logger.warning("Could not audit indexes: %s", exc)

        # Ensure correct compound unique index
        try:
            self.db.narratives.create_index(
                [("narrative_id", ASCENDING), ("user_id", ASCENDING)],
                unique=True,
                name="narrative_id_user_unique",
            )
        except Exception:
            pass  # already exists

        try:
            self.db.narratives.create_index(
                [("user_id", ASCENDING), ("confidence_score", DESCENDING)],
                name="user_confidence",
            )
        except Exception:
            pass

        # ── narrative_history (time series) ──────────────────────────────────
        if "narrative_history" not in existing:
            try:
                self.db.create_collection(
                    "narrative_history",
                    timeseries={
                        "timeField": "recorded_at",
                        "metaField": "narrative_id",   # stable ID, not name
                        "granularity": "hours",
                    },
                )
                logger.info("Created MongoDB time series collection: narrative_history")
            except (CollectionInvalid, OperationFailure) as exc:
                logger.warning("Could not create time series collection: %s", exc)

    # ── Write ──────────────────────────────────────────────────────────────────

    def save_narratives(self, narratives: List[Dict[str, Any]], user_id: str = "default") -> None:
        now = datetime.now(timezone.utc)
        for narrative in narratives:
            narrative_id = make_narrative_id(narrative)

            doc = {
                **narrative,
                "narrative_id": narrative_id,
                "tracked":      False,
                "user_id":      user_id,
                "updated_at":   now,
            }

            # Normalise detected_at to datetime
            if isinstance(doc.get("detected_at"), str):
                try:
                    doc["detected_at"] = datetime.fromisoformat(doc["detected_at"].replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    doc["detected_at"] = now
            elif not isinstance(doc.get("detected_at"), datetime):
                doc["detected_at"] = now

            # Only set detected_at on first insert; preserve original on update
            self.db.narratives.update_one(
                {"narrative_id": narrative_id, "user_id": user_id},
                {
                    "$set": {k: v for k, v in doc.items() if k != "detected_at"},
                    "$setOnInsert": {"detected_at": doc["detected_at"]},
                },
                upsert=True,
            )
            logger.debug("Upserted narrative %s for user %s", narrative_id, user_id)

            # Append snapshot to time series
            momentum = narrative.get("momentum") or {}
            momentum_score = momentum.get("momentum_score", 0) if isinstance(momentum, dict) else 0
            try:
                self.db.narrative_history.insert_one({
                    "recorded_at":      now,
                    "narrative_id":     narrative_id,   # metaField
                    "narrative_name":   narrative.get("name"),
                    "category":         narrative.get("category"),
                    "status":           narrative.get("status"),
                    "strength":         narrative.get("strength"),
                    "confidence_score": narrative.get("confidence_score"),
                    "momentum_score":   momentum_score,
                    "user_id":          user_id,
                })
            except Exception as exc:
                logger.warning("Could not insert history snapshot for %s: %s", narrative_id, exc)

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_current_narratives(
        self, user_id: str = "default", min_confidence: float = 0.5
    ) -> List[Dict[str, Any]]:
        return list(
            self.db.narratives.find(
                {"user_id": user_id, "confidence_score": {"$gte": min_confidence}},
                {"_id": 0},
            )
            .sort("confidence_score", DESCENDING)
            .limit(50)
        )

    def get_narratives_summary(self, user_id: str = "default") -> List[Dict[str, Any]]:
        """
        Compact summary of all active narratives — passed to Gemini as history context.
        Includes prior evidence and momentum so Gemini can evolve rather than recreate.
        """
        now = datetime.now(timezone.utc)
        docs = list(
            self.db.narratives.find(
                {"user_id": user_id},
                {
                    "_id": 0,
                    "narrative_id": 1,
                    "name": 1,
                    "category": 1,
                    "status": 1,
                    "confidence_score": 1,
                    "strength": 1,
                    "detected_at": 1,
                    "updated_at": 1,
                    "top_tokens": 1,
                    "key_evidence": 1,
                    "signal_sources": 1,
                    "momentum": 1,
                },
            )
            .sort("confidence_score", DESCENDING)
            .limit(20)
        )
        for doc in docs:
            updated = doc.get("updated_at")
            if isinstance(updated, datetime):
                updated_utc = updated if updated.tzinfo else updated.replace(tzinfo=timezone.utc)
                doc["hours_since_update"] = int((now - updated_utc).total_seconds() / 3600)
            else:
                doc["hours_since_update"] = None
        return docs

    def mark_stale_narratives(self, returned_ids: set, user_id: str = "default") -> None:
        """
        For active narratives NOT returned by Gemini in this run, set status=STABLE
        if they were updated within the last 72 hours. Prevents silent disappearance.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
        self.db.narratives.update_many(
            {
                "user_id":    user_id,
                "narrative_id": {"$nin": list(returned_ids)},
                "updated_at": {"$gte": cutoff},
                "status":     {"$nin": ["STABLE", "REVERSING"]},
            },
            {
                "$set": {
                    "status":           "STABLE",
                    "momentum.trend":   "weakening",
                    "updated_at":       datetime.now(timezone.utc),
                }
            },
        )

    def get_tracked_narratives(self, user_id: str = "default") -> List[Dict[str, Any]]:
        return list(
            self.db.narratives.find(
                {"user_id": user_id, "tracked": True},
                {"_id": 0},
            )
            .sort("updated_at", DESCENDING)
            .limit(50)
        )

    def get_narrative_history(
        self,
        narrative_id: str,
        days: int = 7,
        user_id: str = "default",
    ) -> List[Dict[str, Any]]:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        return list(
            self.db.narrative_history.find(
                {
                    "narrative_id": narrative_id,
                    "user_id":      user_id,
                    "recorded_at":  {"$gte": since},
                },
                {"_id": 0},
            )
            .sort("recorded_at", ASCENDING)
            .limit(1000)
        )

    def get_narrative_by_id(
        self, narrative_id: str, user_id: str = "default"
    ) -> Optional[Dict[str, Any]]:
        return self.db.narratives.find_one(
            {"narrative_id": narrative_id, "user_id": user_id},
            {"_id": 0},
        )

    def get_narrative_by_category(
        self, category: str, user_id: str = "default"
    ) -> List[Dict[str, Any]]:
        return list(
            self.db.narratives.find(
                {"category": category, "user_id": user_id},
                {"_id": 0},
            )
            .sort("confidence_score", DESCENDING)
            .limit(50)
        )

    def get_strengthening_narratives(self, user_id: str = "default") -> List[Dict[str, Any]]:
        return list(
            self.db.narratives.find(
                {"user_id": user_id, "momentum.trend": "strengthening"},
                {"_id": 0},
            )
            .sort("momentum.momentum_score", DESCENDING)
            .limit(50)
        )

    def track_narrative(self, narrative_id: str, user_id: str = "default") -> None:
        self.db.narratives.update_one(
            {"narrative_id": narrative_id, "user_id": user_id},
            {"$set": {"tracked": True, "updated_at": datetime.now(timezone.utc)}},
        )

    def untrack_narrative(self, narrative_id: str, user_id: str = "default") -> None:
        self.db.narratives.update_one(
            {"narrative_id": narrative_id, "user_id": user_id},
            {"$set": {"tracked": False, "updated_at": datetime.now(timezone.utc)}},
        )

    def get_narrative_stats(self, user_id: str = "default") -> Dict[str, Any]:
        return {
            "total_narratives": self.db.narratives.count_documents({"user_id": user_id}),
            "tracked_narratives": self.db.narratives.count_documents(
                {"user_id": user_id, "tracked": True}
            ),
            "strengthening_narratives": self.db.narratives.count_documents(
                {"user_id": user_id, "momentum.trend": "strengthening"}
            ),
        }
