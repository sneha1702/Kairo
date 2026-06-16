"""
Module-level singletons initialized lazily on first call and reused for the process lifetime.
"""
import os
import time
import logging
from typing import Optional, Tuple, Any

logger = logging.getLogger(__name__)

# ── Singletons ────────────────────────────────────────────────────────────────

_user_manager: Any = None
_user_manager_ready: bool = False

_services: Optional[Tuple] = None
_services_ready: bool = False

_concept_tracker: Any = None
_concept_tracker_ready: bool = False

_regulation_tracker: Any = None
_regulation_tracker_ready: bool = False


def _cfg(key: str, default: str = "") -> str:
    """Read from env, then Config class, falling back to default."""
    try:
        from config.config import Config
        return os.getenv(key, getattr(Config, key, default) or default)
    except Exception:
        return os.getenv(key, default)


def get_user_manager():
    global _user_manager, _user_manager_ready
    if _user_manager_ready:
        return _user_manager
    _user_manager_ready = True
    mongo_uri = _cfg("MONGO_URI")
    mongo_db = _cfg("MONGO_DB") or "kairo"
    if not mongo_uri:
        logger.warning("MONGO_URI not set — UserManager unavailable.")
        return None
    try:
        from app.auth.user_manager import UserManager
        mgr = UserManager(mongo_uri, mongo_db)
        bootstrap = mgr.ensure_default_admin()
        if bootstrap:
            u, p = bootstrap
            logger.warning("Bootstrap admin created — username=%s password=%s", u, p)
        _user_manager = mgr
    except Exception as exc:
        logger.warning("UserManager init failed: %s", exc)
    return _user_manager


def get_services() -> Tuple[Any, Any, Any]:
    """Return (es_manager, narrative_engine, tracker)."""
    global _services, _services_ready
    if _services_ready:
        return _services
    _services_ready = True

    from app.synthesize.narrative_engine import NarrativeEngine
    from app.synthesize.narrative_tracker import NarrativeTracker
    from app.brain.elasticsearch_manager import ElasticsearchManager

    demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"
    gemini_key = _cfg("GEMINI_KEY")
    es_url = _cfg("ES_URL")
    mongo_uri = _cfg("MONGO_URI")
    mongo_db = _cfg("MONGO_DB") or "kairo"

    if demo_mode:
        engine = NarrativeEngine(gemini_key) if gemini_key else None
        _services = (None, engine, None)
        return _services

    es_manager = None
    if es_url:
        try:
            es_manager = ElasticsearchManager(
                es_url, _cfg("ES_USERNAME"), _cfg("ES_PASSWORD"), _cfg("ES_API_KEY_ID"),
            )
        except Exception as exc:
            logger.info("ES unavailable: %s", exc)

    narrative_engine = None
    if gemini_key:
        try:
            narrative_engine = NarrativeEngine(gemini_key)
        except Exception as exc:
            logger.info("Gemini unavailable: %s", exc)

    tracker = None
    if mongo_uri:
        try:
            tracker = NarrativeTracker(mongo_uri, mongo_db)
        except Exception as exc:
            logger.warning("NarrativeTracker init failed: %s", exc)

    _services = (es_manager, narrative_engine, tracker)
    return _services


def get_concept_tracker():
    global _concept_tracker, _concept_tracker_ready
    if _concept_tracker_ready:
        return _concept_tracker
    _concept_tracker_ready = True
    mongo_uri = _cfg("MONGO_URI")
    mongo_db = _cfg("MONGO_DB") or "kairo"
    if not mongo_uri:
        return None
    try:
        from app.education.concept_tracker import ConceptTracker
        _concept_tracker = ConceptTracker(mongo_uri, mongo_db)
    except Exception as exc:
        logger.warning("ConceptTracker init failed: %s", exc)
    return _concept_tracker


def get_regulation_tracker():
    global _regulation_tracker, _regulation_tracker_ready
    if _regulation_tracker_ready:
        return _regulation_tracker
    _regulation_tracker_ready = True
    mongo_uri = _cfg("MONGO_URI")
    mongo_db = _cfg("MONGO_DB") or "kairo"
    if not mongo_uri:
        return None
    try:
        from app.regulations.regulation_tracker import RegulationTracker
        _regulation_tracker = RegulationTracker(mongo_uri, mongo_db)
    except Exception as exc:
        logger.warning("RegulationTracker init failed: %s", exc)
    return _regulation_tracker


# ── Data cache (TTL 5 minutes) ────────────────────────────────────────────────

_data_cache: dict = {}


def get_cached_build_data(user_id: str, hours: int = 0) -> dict:
    from config.config import Config
    if hours <= 0:
        hours = Config.DUNE_QUERY_WINDOW_HOURS
    key = (user_id, hours)
    entry = _data_cache.get(key)
    if entry and time.time() - entry["ts"] < 300:
        return entry["data"]
    try:
        es_manager, _engine, tracker = get_services()
        from app.synthesize.kairo_data import build_kairo_data
        data = build_kairo_data(
            es_manager=es_manager,
            tracker=tracker,
            dune_context={},
            user_id=user_id,
        )
    except Exception as exc:
        logger.exception("get_cached_build_data failed: %s", exc)
        from app.synthesize.kairo_data import _empty_data
        data = _empty_data()
    _data_cache[key] = {"ts": time.time(), "data": data}
    return data


def invalidate_data_cache() -> None:
    _data_cache.clear()
