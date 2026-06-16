import json
import os
import logging
from datetime import datetime, timezone

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from web.services import (
    get_user_manager, get_services, get_concept_tracker,
    get_regulation_tracker, get_cached_build_data, invalidate_data_cache,
    _cfg,
)
from app.app import build_kairo_html, _KairoEncoder

logger = logging.getLogger(__name__)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _session_user(request):
    return request.session.get("_kairo_user")


def _authenticate_request(request):
    """Return (user, None) or (None, redirect). Validates remember-me cookie too."""
    user = _session_user(request)
    if not user:
        token = request.COOKIES.get("kairo_session", "")
        if token:
            mgr = get_user_manager()
            if mgr:
                try:
                    uname = mgr.validate_session_token(token)
                    if uname:
                        profile = mgr.get_profile(uname)
                        if profile:
                            request.session["_kairo_user"] = profile
                            request.session["_kairo_session_token"] = token
                            return profile, None
                except Exception as exc:
                    logger.warning("remember-me validation failed: %s", exc)
        return None, redirect("/login/")
    return user, None


# ── Main app ──────────────────────────────────────────────────────────────────

def index(request):
    user, redir = _authenticate_request(request)
    if redir:
        return redir

    from config.config import Config as _Cfg
    user_id = "default"
    hours = _Cfg.DUNE_QUERY_WINDOW_HOURS

    kairo_data = get_cached_build_data(user_id, hours)
    kairo_data.setdefault("config", {})["dune_query_window_hours"] = _Cfg.DUNE_QUERY_WINDOW_HOURS
    kairo_data["auth_user"] = dict(user)
    kairo_data["config"]["is_admin"] = user.get("role") == "admin"
    kairo_data["config"]["admin_url"] = "/admin-panel/"

    try:
        reg_trk = get_regulation_tracker()
        if reg_trk:
            kairo_data["regulations"] = reg_trk.get_latest_regulations(limit=60)
            kairo_data["regulation_last_run"] = reg_trk.get_last_run() or {}
        else:
            kairo_data.setdefault("regulations", [])
            kairo_data.setdefault("regulation_last_run", {})
    except Exception as exc:
        logger.warning("Failed to load regulations: %s", exc)
        kairo_data.setdefault("regulations", [])
        kairo_data.setdefault("regulation_last_run", {})

    try:
        con_trk = get_concept_tracker()
        if con_trk:
            kairo_data["concepts"] = con_trk.get_all_concepts()
            kairo_data["concept_groups"] = con_trk.get_all_groups()
        else:
            kairo_data.setdefault("concepts", [])
            kairo_data.setdefault("concept_groups", [])
    except Exception as exc:
        logger.warning("Failed to load concepts: %s", exc)
        kairo_data.setdefault("concepts", [])
        kairo_data.setdefault("concept_groups", [])

    for sess_key, cfg_key in [
        ("_kairo_init_view", "initial_view"),
        ("_kairo_toast", "toast"),
        ("_kairo_pw_result", "pw_result"),
        ("_kairo_pw_message", "pw_message"),
    ]:
        val = request.session.pop(sess_key, None)
        if val:
            kairo_data["config"][cfg_key] = val

    try:
        data_json = json.dumps(kairo_data, cls=_KairoEncoder, ensure_ascii=False)
    except Exception as exc:
        logger.exception("JSON serialisation failed: %s", exc)
        from app.synthesize.kairo_data import _empty_data
        data_json = json.dumps(_empty_data(), ensure_ascii=False)

    return HttpResponse(build_kairo_html(data_json), content_type="text/html")


# ── Login / logout ────────────────────────────────────────────────────────────

def login_view(request):
    if _session_user(request):
        return redirect("/")
    error = request.session.pop("_login_error", None)
    return render(request, "login.html", {"error": error})


@csrf_exempt
@require_http_methods(["POST"])
def api_login(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    remember_me = bool(data.get("remember_me"))

    mgr = get_user_manager()
    if mgr is None:
        return JsonResponse({"ok": False, "error": "Sign-in temporarily unavailable."}, status=503)

    from app.auth.user_manager import AuthError
    generic_err = "Those credentials didn't match. Please try again."
    try:
        user = mgr.authenticate(username, password)
    except AuthError as exc:
        user = None
        if getattr(exc, "code", None) == "locked":
            generic_err = str(exc)

    if not user:
        return JsonResponse({"ok": False, "error": generic_err})

    request.session.cycle_key()
    request.session["_kairo_user"] = user

    from config.config import Config
    response = JsonResponse({"ok": True, "redirect": "/"})
    if remember_me:
        try:
            token = mgr.create_session_token(user["username"])
            request.session["_kairo_session_token"] = token
            response.set_cookie(
                "kairo_session", token,
                max_age=30 * 24 * 3600,
                httponly=True,
                samesite="Lax",
                secure=not Config.DEBUG,
            )
        except Exception as exc:
            logger.warning("remember-me token creation failed: %s", exc)

    return response


@csrf_exempt
@require_http_methods(["POST"])
def api_register(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid request."}, status=400)

    from app.auth.user_manager import AuthError, validate_password, validate_username

    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    email = (data.get("email") or "").strip()
    agreed = bool(data.get("agreed"))

    err = validate_username(username)
    if err:
        return JsonResponse({"ok": False, "error": err})
    err = validate_password(password)
    if err:
        return JsonResponse({"ok": False, "error": err})
    if not agreed:
        return JsonResponse({"ok": False, "error": "Please accept the educational-use notice."})

    mgr = get_user_manager()
    if mgr is None:
        return JsonResponse({"ok": False, "error": "Account creation temporarily unavailable."}, status=503)

    try:
        ok = mgr.create_user(username, password, role="user", email=email)
    except AuthError as exc:
        return JsonResponse({"ok": False, "error": str(exc)})

    if ok:
        return JsonResponse({"ok": True, "message": "Account created. Sign in to continue."})
    return JsonResponse({"ok": False, "error": "Couldn't create that account. Try a different username."})


def logout_view(request):
    token = (
        request.session.get("_kairo_session_token")
        or request.COOKIES.get("kairo_session", "")
    )
    if token:
        try:
            mgr = get_user_manager()
            if mgr:
                mgr.invalidate_session_token(token)
        except Exception:
            logger.warning("Session invalidation failed during logout.")

    request.session.flush()
    invalidate_data_cache()

    response = redirect("/login/")
    response.delete_cookie("kairo_session")
    return response


# ── Profile API ───────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def api_profile_save(request):
    user, redir = _authenticate_request(request)
    if redir:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)
    try:
        updates = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)

    mgr = get_user_manager()
    if not mgr:
        return JsonResponse({"ok": False, "error": "Service unavailable."}, status=503)

    try:
        mgr.update_profile(user["username"], updates)
        refreshed = mgr.get_profile(user["username"])
        if refreshed:
            request.session["_kairo_user"] = refreshed
    except Exception as exc:
        logger.warning("Profile save failed: %s", exc)
        return JsonResponse({"ok": False, "error": str(exc)})

    return JsonResponse({"ok": True})


@csrf_exempt
@require_http_methods(["POST"])
def api_password_change(request):
    user, redir = _authenticate_request(request)
    if redir:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)

    from app.auth.user_manager import AuthError
    mgr = get_user_manager()
    if not mgr:
        return JsonResponse({"ok": False, "error": "Service unavailable."}, status=503)

    try:
        ok = mgr.change_password(user["username"], data.get("old", ""), data.get("new", ""))
    except AuthError as exc:
        return JsonResponse({"ok": False, "error": str(exc), "code": getattr(exc, "code", "error")})

    if ok:
        try:
            token = mgr.create_session_token(user["username"])
            request.session["_kairo_session_token"] = token
        except Exception:
            pass
        return JsonResponse({"ok": True})
    return JsonResponse({"ok": False, "error": "Password change failed."})


@csrf_exempt
@require_http_methods(["POST"])
def api_delete_account(request):
    user, redir = _authenticate_request(request)
    if redir:
        return JsonResponse({"ok": False, "error": "Not authenticated."}, status=401)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)

    if data.get("confirm_user") != user["username"]:
        return JsonResponse({"ok": False, "error": "Username confirmation did not match."})

    mgr = get_user_manager()
    if mgr:
        mgr.delete_user(user["username"])

    request.session.flush()
    invalidate_data_cache()
    response = JsonResponse({"ok": True, "redirect": "/login/"})
    response.delete_cookie("kairo_session")
    return response


# ── Admin panel ───────────────────────────────────────────────────────────────

def _require_admin(request):
    user, redir = _authenticate_request(request)
    if redir:
        return None, redir
    if user.get("role") != "admin":
        return None, HttpResponse("Forbidden", status=403)
    return user, None


def admin_panel(request):
    user, redir = _require_admin(request)
    if redir:
        return redir

    _es, _engine, tracker = get_services()
    stats = {}
    if tracker:
        try:
            stats = tracker.get_narrative_stats("default")
        except Exception:
            pass

    from config.config import Config as _Cfg
    flash = request.session.pop("_admin_flash", None)
    return render(request, "admin_panel.html", {
        "user": user,
        "stats": stats,
        "flash": flash,
        "ingestion_provider": _Cfg.INGESTION_PROVIDER,
        "dune_query_window_hours": _Cfg.DUNE_QUERY_WINDOW_HOURS,
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_admin_run_detection(request):
    _, redir = _require_admin(request)
    if redir:
        return JsonResponse({"ok": False, "error": "Forbidden."}, status=403)
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    from config.config import Config as _Cfg
    hours = int(data.get("hours", _Cfg.DUNE_QUERY_WINDOW_HOURS))
    user_id = data.get("user_id", "default")

    es, engine, tracker = get_services()
    if not es or not engine:
        return JsonResponse({"ok": False, "error": "ES or Gemini not configured."})

    try:
        from app.synthesize.signal_transformer import SignalTransformer, enrich_with_acceleration
        transformer = SignalTransformer(es)
        unified_signals = transformer.build_unified_signals(hours=hours)
        unified_signals = enrich_with_acceleration(unified_signals, es)
        dune_context = es.get_dune_signal_context(hours=hours)
        history_summary = tracker.get_narratives_summary(user_id) if tracker else []
        current_narratives = tracker.get_current_narratives(user_id, min_confidence=0.0) if tracker else []

        new_narratives = engine.detect_narratives(
            dune_context=dune_context,
            historical_narratives=history_summary,
            unified_signals=unified_signals,
        ) or []

        enriched = [engine.enrich_narrative(n, previous_narratives=current_narratives) for n in new_narratives]

        if enriched and tracker:
            signal_meta = {
                "window_hours": hours,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_records": len(unified_signals),
            }
            for n in enriched:
                n["unified_signals"] = unified_signals
                n["signal_metadata"] = signal_meta
            tracker.save_narratives(enriched, user_id)
            tracker.mark_stale_narratives({n.get("narrative_id") for n in enriched}, user_id)

        invalidate_data_cache()
        return JsonResponse({"ok": True, "message": f"{len(enriched)} narrative(s) detected and saved."})
    except Exception as exc:
        logger.exception("Detection failed")
        return JsonResponse({"ok": False, "error": str(exc)})


@csrf_exempt
@require_http_methods(["POST"])
def api_admin_run_ingestion(request):
    _, redir = _require_admin(request)
    if redir:
        return JsonResponse({"ok": False, "error": "Forbidden."}, status=403)
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    source = data.get("source", "narratives")
    mongo_uri = _cfg("MONGO_URI")
    mongo_db = _cfg("MONGO_DB") or "kairo"

    try:
        if source == "narratives":
            from config.config import Config as _Cfg
            from datetime import datetime as _dt
            if _Cfg.INGESTION_PROVIDER == "dune":
                from app.ingestion.dune_pipeline import build_pipeline
            else:
                from app.ingestion.defillama_pipeline import build_defillama_pipeline as build_pipeline
            pipeline = build_pipeline()
            end_str = _dt.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            res = pipeline.run_all(end_time=end_str, time_window_hours=24)
            total_rows = sum(getattr(r, "rows_fetched", 0) for r in res.values()) if hasattr(res, "values") else 0
            invalidate_data_cache()
            return JsonResponse({"ok": True, "message": f"Ingestion complete — {total_rows} rows fetched."})

        elif source == "markets":
            cmc_key = _cfg("CMC_API_KEY")
            if not cmc_key:
                return JsonResponse({"ok": False, "error": "CMC_API_KEY not configured."})
            from app.ingestion.crypto_markets import CryptoMarketsUpdater
            upd = CryptoMarketsUpdater(cmc_key, mongo_uri, mongo_db)
            projects = upd.build_projects(discover_roadmaps=bool(data.get("discover_roadmaps")))
            upd.save_to_mongo(projects)
            from app.markets.analyzer import MarketAnalyzer
            analyzer = MarketAnalyzer(mongo_uri, mongo_db)
            results = analyzer.analyze_all(fetch_pages=False, dry_run=False)
            ok_count = sum(1 for r in results if not r.get("analysis_error"))
            invalidate_data_cache()
            return JsonResponse({"ok": True, "message": f"Updated {len(projects)} projects, {ok_count} analysed."})

        elif source == "policy":
            _es, engine, _ = get_services()
            reg_trk = get_regulation_tracker()
            if not reg_trk or not engine:
                return JsonResponse({"ok": False, "error": "RegulationTracker or Gemini not configured."})
            result = reg_trk.fetch_and_store(engine)
            saved = result.get("saved", 0)
            skipped = result.get("skipped", 0)
            if "error" in result:
                return JsonResponse({"ok": False, "error": result["error"]})
            invalidate_data_cache()
            return JsonResponse({"ok": True, "message": f"{saved} regulation(s) added, {skipped} already known."})

        elif source == "concepts":
            _es, engine, _ = get_services()
            con_trk = get_concept_tracker()
            if not con_trk or not engine:
                return JsonResponse({"ok": False, "error": "ConceptTracker or Gemini not configured."})
            source_url = (data.get("source_url") or "").strip()
            result = con_trk.fetch_and_store_from_url(engine, source_url)
            if "error" in result:
                return JsonResponse({"ok": False, "error": result["error"]})
            saved = result.get("saved", 0)
            skipped = result.get("skipped", 0)
            invalidate_data_cache()
            return JsonResponse({"ok": True, "message": f"{saved} concept(s) added, {skipped} already known."})

        else:
            return JsonResponse({"ok": False, "error": f"Unknown source: {source}"})

    except Exception as exc:
        logger.exception("Ingestion failed for source=%s", source)
        return JsonResponse({"ok": False, "error": str(exc)})


@csrf_exempt
@require_http_methods(["POST"])
def api_admin_purge(request):
    _, redir = _require_admin(request)
    if redir:
        return JsonResponse({"ok": False, "error": "Forbidden."}, status=403)
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    source = data.get("source")
    mongo_uri = _cfg("MONGO_URI")
    mongo_db = _cfg("MONGO_DB") or "kairo"

    try:
        if source == "narratives":
            _es, _engine, tracker = get_services()
            if not tracker:
                return JsonResponse({"ok": False, "error": "MongoDB tracker not connected."})
            n = tracker.purge_narratives("default")
            invalidate_data_cache()
            return JsonResponse({"ok": True, "message": f"Deleted {n} narrative(s)."})

        elif source in ("markets", "policy", "concepts"):
            from pymongo import MongoClient
            from config.config import mongo_tls_ca_file
            from pymongo.server_api import ServerApi
            client = MongoClient(
                mongo_uri, tlsCAFile=mongo_tls_ca_file(),
                server_api=ServerApi("1"), connect=False,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
            )
            db = client[mongo_db]
            collection_map = {
                "markets":  ["crypto_markets_config"],
                "policy":   ["crypto_regulations", "regulation_runs"],
                "concepts": ["concepts", "concept_groups"],
            }
            for col in collection_map[source]:
                db[col].drop()
            client.close()
            invalidate_data_cache()
            return JsonResponse({"ok": True, "message": f"{source.capitalize()} data purged."})

        else:
            return JsonResponse({"ok": False, "error": f"Unknown source: {source}"})

    except Exception as exc:
        logger.exception("Purge failed for source=%s", source)
        return JsonResponse({"ok": False, "error": str(exc)})


@csrf_exempt
@require_http_methods(["POST"])
def api_admin_backfill(request):
    _, redir = _require_admin(request)
    if redir:
        return JsonResponse({"ok": False, "error": "Forbidden."}, status=403)
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    source = data.get("source", "narratives")
    days = int(data.get("days", 7))
    user_id = data.get("user_id", "default")
    fetch_fresh = bool(data.get("fetch_fresh"))

    es, engine, tracker = get_services()

    try:
        if source == "narratives":
            if not es or not engine:
                return JsonResponse({"ok": False, "error": "ES or Gemini not configured."})

            if fetch_fresh:
                from config.config import Config as _Cfg
                from datetime import timedelta
                from datetime import datetime as _dt
                if _Cfg.INGESTION_PROVIDER == "dune":
                    from app.ingestion.dune_pipeline import build_pipeline
                else:
                    from app.ingestion.defillama_pipeline import build_defillama_pipeline as build_pipeline
                pipeline = build_pipeline()
                chunk_hours = 168
                n_chunks = (days + 6) // 7
                for i in range(n_chunks):
                    chunk_end = _dt.now(timezone.utc) - timedelta(weeks=i)
                    try:
                        pipeline.run_all(
                            end_time=chunk_end.strftime("%Y-%m-%d %H:%M:%S"),
                            time_window_hours=chunk_hours,
                        )
                    except Exception as exc:
                        logger.warning("On-chain backfill chunk %d failed: %s", i, exc)

            from app.synthesize.signal_transformer import run_narrative_generation
            chunk_hours = 168
            total_hours = days * 24
            windows = list(range(total_hours, 0, -chunk_hours)) or [total_hours]
            total_saved = 0
            prior = None
            for w_hours in windows:
                try:
                    result = run_narrative_generation(
                        hours=w_hours, user_id=user_id,
                        es_manager=es, engine=engine, tracker=tracker,
                        dry_run=False, prior_narratives=prior,
                    )
                    total_saved += len(result)
                    prior = result or prior
                except Exception as exc:
                    logger.warning("Backfill window %dh failed: %s", w_hours, exc)

            invalidate_data_cache()
            return JsonResponse({
                "ok": True,
                "message": f"Backfill complete — {total_saved} narrative(s) across {len(windows)} window(s).",
            })

        elif source == "policy":
            _es, policy_engine, _ = get_services()
            reg_trk = get_regulation_tracker()
            if not reg_trk or not policy_engine:
                return JsonResponse({"ok": False, "error": "RegulationTracker or Gemini not configured."})
            if fetch_fresh:
                result = reg_trk.fetch_and_store(policy_engine)
                if "error" in result:
                    return JsonResponse({"ok": False, "error": result["error"]})
                saved = result.get("saved", 0)
                skipped = result.get("skipped", 0)
                invalidate_data_cache()
                return JsonResponse({"ok": True, "message": f"{saved} regulation(s) added, {skipped} already known."})
            else:
                return JsonResponse({"ok": True, "message": "No fresh fetch requested — existing data retained."})

        else:
            return JsonResponse({"ok": False, "error": f"Backfill not supported for: {source}"})

    except Exception as exc:
        logger.exception("Backfill failed for source=%s", source)
        return JsonResponse({"ok": False, "error": str(exc)})
