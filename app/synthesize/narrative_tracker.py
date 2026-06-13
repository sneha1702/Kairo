"""
Narrative Tracker: Persists and retrieves narratives over time.
Uses MongoDB for current narrative state and a time series collection for history.

Deduplication strategy:
  Each narrative is identified by a stable (narrative_id, user_id) pair.
  Gemini is instructed to reuse known narrative_ids for the same theme.
  Fallback: if Gemini omits narrative_id, one is generated from the name.
  Upsert key: narrative_id + user_id  →  one doc per theme per user.
"""

import json
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import CollectionInvalid, OperationFailure
from pymongo.server_api import ServerApi

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"


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
        logger.info("[MONGO] Connecting to MongoDB, db=%s", db_name)
        from config.config import mongo_tls_ca_file
        self.client = MongoClient(
            mongo_uri,
            tlsCAFile=mongo_tls_ca_file(),
            serverSelectionTimeoutMS=2000,
            connectTimeoutMS=2000,
            socketTimeoutMS=5000,
        )
        self.db = self.client[db_name]
        # Force an actual connection attempt so failures surface here rather than lazily.
        self.client.admin.command("ping")
        logger.info("[MONGO] Connected — db=%s", db_name)
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
        ts = now.strftime("%Y%m%d_%H%M%S")
        logger.info("[MONGO] Persisting %d narratives for user=%s", len(narratives), user_id)

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

            # Normalise evidence_timestamps: flatten per-token ISO strings to datetime
            raw_et = doc.get("evidence_timestamps")
            if isinstance(raw_et, dict):
                _normalized_et: dict = {}
                for tok, tok_data in raw_et.items():
                    if not isinstance(tok_data, dict):
                        _normalized_et[tok] = tok_data
                        continue
                    _tok_norm: dict = {}
                    for k, v in tok_data.items():
                        if isinstance(v, str) and len(v) >= 10:
                            try:
                                _tok_norm[k] = datetime.fromisoformat(v.replace("Z", "+00:00"))
                            except (ValueError, TypeError):
                                _tok_norm[k] = v
                        elif isinstance(v, list):
                            _parsed = []
                            for item in v:
                                if isinstance(item, str) and len(item) >= 10:
                                    try:
                                        _parsed.append(datetime.fromisoformat(item.replace("Z", "+00:00")))
                                    except (ValueError, TypeError):
                                        _parsed.append(item)
                                else:
                                    _parsed.append(item)
                            _tok_norm[k] = _parsed
                        else:
                            _tok_norm[k] = v
                    _normalized_et[tok] = _tok_norm
                doc["evidence_timestamps"] = _normalized_et

            # Normalise provenance timestamp strings to datetime
            for ts_field in ("data_window_start", "data_window_end", "last_ingested_at", "prompt_built_at"):
                raw = doc.get(ts_field)
                if isinstance(raw, str) and raw:
                    try:
                        doc[ts_field] = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        doc[ts_field] = None

            # Evolution log entry — appended on every update, capped at 100 entries
            evolution_entry = {
                "updated_at":          now,
                "status":              narrative.get("status"),
                "confidence_score":    narrative.get("confidence_score"),
                "strength":            narrative.get("strength"),
                "momentum_trend":      (narrative.get("momentum") or {}).get("trend", ""),
                "data_window_start":   doc.get("data_window_start"),
                "data_window_end":     doc.get("data_window_end"),
                "last_ingested_at":    doc.get("last_ingested_at"),
                "key_evidence":        (narrative.get("key_evidence") or [])[:3],
                "evidence_timestamps": doc.get("evidence_timestamps"),
            }

            # Only set detected_at on first insert; preserve original on update
            result = self.db.narratives.update_one(
                {"narrative_id": narrative_id, "user_id": user_id},
                {
                    "$set": {k: v for k, v in doc.items() if k != "detected_at"},
                    "$setOnInsert": {"detected_at": doc["detected_at"]},
                    "$push": {
                        "evolution_log": {
                            "$each":  [evolution_entry],
                            "$slice": -100,   # keep last 100 evolution snapshots
                        }
                    },
                },
                upsert=True,
            )
            action = "inserted" if result.upserted_id else "updated"
            logger.info(
                "[MONGO] Narrative %-40s %s (status=%s, confidence=%.2f, data_window=%s→%s)",
                narrative_id, action,
                narrative.get("status", "?"),
                narrative.get("confidence_score", 0),
                narrative.get("data_window_start", "?"),
                narrative.get("data_window_end", "?"),
            )

            # Append snapshot to time series
            momentum = narrative.get("momentum") or {}
            momentum_score = momentum.get("momentum_score", 0) if isinstance(momentum, dict) else 0
            try:
                self.db.narrative_history.insert_one({
                    "recorded_at":       now,
                    "narrative_id":      narrative_id,   # metaField
                    "narrative_name":    narrative.get("name"),
                    "category":          narrative.get("category"),
                    "status":            narrative.get("status"),
                    "strength":          narrative.get("strength"),
                    "confidence_score":  narrative.get("confidence_score"),
                    "momentum_score":    momentum_score,
                    "data_window_start": doc.get("data_window_start"),
                    "data_window_end":   doc.get("data_window_end"),
                    "last_ingested_at":  doc.get("last_ingested_at"),
                    "user_id":           user_id,
                })
            except Exception as exc:
                logger.warning("[MONGO] Could not insert history snapshot for %s: %s", narrative_id, exc)

        # ── Persist snapshot to outputs/ ──────────────────────────────────────
        try:
            _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_file = _OUTPUT_DIR / f"narratives_{ts}.json"

            def _default(obj: Any) -> str:
                if isinstance(obj, datetime):
                    return obj.isoformat()
                return str(obj)

            output_file.write_text(
                json.dumps(narratives, indent=2, default=_default),
                encoding="utf-8",
            )
            logger.info("[MONGO] Narratives snapshot saved → %s", output_file)
        except Exception as exc:
            logger.warning("[MONGO] Could not write narratives snapshot: %s", exc)

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
                    "data_window_start": 1,
                    "data_window_end": 1,
                    "last_ingested_at": 1,
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

    def purge_narratives(self, user_id: str = "default") -> int:
        """Delete all narratives for a user. Returns the number of documents deleted."""
        result = self.db.narratives.delete_many({"user_id": user_id})
        deleted = result.deleted_count
        logger.info("[MONGO] Purged %d narratives for user=%s", deleted, user_id)
        return deleted

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
