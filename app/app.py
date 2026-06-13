import streamlit as st
import json
import os
import logging
import sys
from datetime import datetime, timezone

from pathlib import Path

ROOT_PATH = Path(__file__).resolve().parents[1]
if str(ROOT_PATH) not in sys.path:
    sys.path.insert(0, str(ROOT_PATH))

from app.brain.elasticsearch_manager import ElasticsearchManager
from app.synthesize.narrative_engine import NarrativeEngine
from app.synthesize.narrative_tracker import NarrativeTracker
from app.synthesize.kairo_data import build_kairo_data

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
# Silence pymongo's server-monitor heartbeat chatter
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("pymongo.topology").setLevel(logging.WARNING)
logging.getLogger("pymongo.serverMonitor").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


# Set autocomplete="off" on Streamlit text inputs so Chrome stops warning about
# the empty autocomplete attribute. Streamlit strips <script> from st.markdown,
# so reach into the parent DOM from a zero-height component iframe.

# ---------------------------------------------------------------------------
# Service initialisation (cached for the lifetime of the Streamlit session)
# ---------------------------------------------------------------------------

@st.cache_resource
def init_services():
    """Initialise ES, Gemini, and MongoDB.  Returns (es_manager, narrative_engine, tracker).
    Each service is initialised independently — one failure does not block the others."""
    from config.config import Config

    def _secret(key: str, default: str = "") -> str:
        try:
            return st.secrets.get(key, os.getenv(key, getattr(Config, key, default) or default))
        except Exception:
            return os.getenv(key, getattr(Config, key, default) or default)

    demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"
    gemini_key = _secret("GEMINI_KEY")
    es_url     = _secret("ES_URL")

    if demo_mode:
        narrative_engine = NarrativeEngine(gemini_key) if gemini_key else None
        return None, narrative_engine, None

    es_username   = _secret("ES_USERNAME")
    es_password   = _secret("ES_PASSWORD")
    es_api_key_id = _secret("ES_API_KEY_ID")
    mongo_uri     = _secret("MONGO_URI")
    mongo_db      = _secret("MONGO_DB") or "kairo"

    es_manager = None
    if es_url:
        try:
            es_manager = ElasticsearchManager(es_url, es_username, es_password, es_api_key_id)
        except Exception as exc:
            logger.warning("ElasticsearchManager init failed: %s", exc)
    else:
        logger.warning("ES_URL not configured — Elasticsearch disabled.")

    narrative_engine = None
    if gemini_key:
        try:
            narrative_engine = NarrativeEngine(gemini_key)
        except Exception as exc:
            logger.warning("NarrativeEngine init failed: %s", exc)
    else:
        logger.warning("GEMINI_KEY not configured — NarrativeEngine disabled.")

    tracker = None
    if mongo_uri:
        try:
            tracker = NarrativeTracker(mongo_uri, mongo_db)
        except Exception as exc:
            logger.warning("NarrativeTracker init failed: %s", exc)
    else:
        logger.warning("MONGO_URI not configured — NarrativeTracker disabled.")

    return es_manager, narrative_engine, tracker


# ---------------------------------------------------------------------------
# Data building (cached for 5 minutes)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _cached_build_data(user_id: str, hours: int = 0) -> dict:
    """Fetch dune_context from ES and build kairo_data. Safe — always returns a dict."""
    if hours <= 0:
        from config.config import Config
        hours = Config.DUNE_QUERY_WINDOW_HOURS
    try:
        es_manager, _engine, tracker = init_services()
        dune_context: dict = {}
        if es_manager is not None:
            try:
                dune_context = es_manager.get_dune_signal_context(hours=hours)
            except Exception as exc:
                logger.warning("get_dune_signal_context failed: %s", exc)

        return build_kairo_data(
            es_manager=es_manager,
            tracker=tracker,
            dune_context=dune_context,
            user_id=user_id,
        )
    except Exception as exc:
        logger.exception("_cached_build_data failed: %s", exc)
        from app.synthesize.kairo_data import _empty_data
        return _empty_data()


# ---------------------------------------------------------------------------
# HTML builder — inlines all design files
# ---------------------------------------------------------------------------

def build_kairo_html(data_json: str) -> str:
    """Return the complete single-file Kairo HTML with real data injected."""

    # ── inline CSS ──────────────────────────────────────────────────────────
    styles_css = r"""/* ============================================================
   Kairo — design tokens & base styles
   Warm, light, novice-first crypto intelligence
   ============================================================ */

:root {
  /* warm paper neutrals */
  --paper:    oklch(0.985 0.006 80);   /* app background */
  --surface:  oklch(0.995 0.004 85);   /* cards */
  --surface-2:oklch(0.965 0.008 80);   /* sunken / chips */
  --hairline: oklch(0.90 0.010 75);
  --hairline-strong: oklch(0.84 0.012 70);

  /* warm ink */
  --ink:      oklch(0.27 0.012 60);    /* headings */
  --ink-2:    oklch(0.42 0.012 60);    /* body */
  --ink-3:    oklch(0.58 0.012 65);    /* muted / labels */
  --ink-4:    oklch(0.70 0.010 70);    /* faint */

  /* primary accent — warm terracotta (tweakable) */
  --accent:        oklch(0.64 0.124 42);
  --accent-soft:   oklch(0.92 0.045 50);
  --accent-ink:    oklch(0.46 0.115 40);

  /* muted pastels — shared L/C, varied hue (Force tags + states) */
  --c-sage:   oklch(0.90 0.050 150);   --c-sage-ink:   oklch(0.50 0.085 150);
  --c-denim:  oklch(0.90 0.050 250);   --c-denim-ink:  oklch(0.50 0.090 252);
  --c-lav:    oklch(0.90 0.050 300);   --c-lav-ink:    oklch(0.50 0.090 300);
  --c-peach:  oklch(0.90 0.050 55);    --c-peach-ink:  oklch(0.52 0.090 50);
  --c-rose:   oklch(0.90 0.050 18);    --c-rose-ink:   oklch(0.52 0.095 22);
  --c-teal:   oklch(0.90 0.050 195);   --c-teal-ink:   oklch(0.50 0.080 198);

  /* directional sentiment (calm, never alarming) */
  --pos:      oklch(0.56 0.085 155);
  --neutral:  oklch(0.62 0.010 70);

  /* typography */
  --font-sans: "Hanken Grotesk", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SF Mono", monospace;

  /* radii & shadow */
  --r-sm: 10px;
  --r-md: 16px;
  --r-lg: 22px;
  --r-xl: 28px;
  --shadow-card: 0 1px 2px oklch(0.5 0.02 60 / 0.05), 0 6px 22px oklch(0.5 0.02 60 / 0.06);
  --shadow-soft: 0 1px 2px oklch(0.5 0.02 60 / 0.04);

  /* layout rhythm (density-tweakable) */
  --gap: 18px;
  --card-pad: 26px;
  --col: 660px;
}

/* density variants */
[data-density="compact"] { --gap: 12px; --card-pad: 20px; }
[data-density="comfy"]   { --gap: 24px; --card-pad: 32px; }

* { box-sizing: border-box; }

html, body {
  margin: 0;
  padding: 0;
  background: var(--paper);
  color: var(--ink-2);
  font-family: var(--font-sans);
  font-size: 16px;
  line-height: 1.55;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

h1, h2, h3, h4 {
  color: var(--ink);
  font-weight: 700;
  line-height: 1.15;
  margin: 0;
  letter-spacing: -0.012em;
  text-wrap: balance;
}

p { margin: 0; text-wrap: pretty; }

a { color: inherit; text-decoration: none; }

button { font-family: inherit; cursor: pointer; border: none; background: none; }

.mono {
  font-family: var(--font-mono);
  font-feature-settings: "tnum" 1;
  letter-spacing: -0.01em;
}

/* eyebrow / section label */
.eyebrow {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: var(--ink-3);
}

::selection { background: var(--accent-soft); }

/* scrollbar */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: var(--hairline-strong); border-radius: 99px; border: 3px solid var(--paper); }
::-webkit-scrollbar-track { background: transparent; }

/* utility: soft card */
.card {
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-card);
}

/* focus ring */
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }

/* fade-in for screen transitions.
   IMPORTANT: animate ONLY transform — never opacity. In some preview iframes the
   animation clock is frozen at t=0; if a keyframe set opacity:0 the content would be
   pinned invisible. Transform-only means a frozen clock just leaves a harmless offset. */
@keyframes kairoFade {
  from { transform: translateY(9px); }
  to   { transform: translateY(0); }
}
@media (prefers-reduced-motion: no-preference) {
  .screen-enter > * {
    animation: kairoFade 0.5s cubic-bezier(0.22, 1, 0.36, 1);
  }
}"""

    # ── layout CSS from Kairo.html's inline <style> block ───────────────────
    layout_css = r"""
    .kairo-app { display: flex; min-height: 100vh; }

    .kairo-rail {
      width: 244px; flex-shrink: 0;
      position: sticky; top: 0; align-self: flex-start; height: 100vh;
      padding: 26px 18px; display: flex; flex-direction: column;
      border-right: 1px solid var(--hairline);
      background: color-mix(in oklch, var(--paper) 60%, var(--surface));
    }
    .kairo-navitems { display: flex; flex-direction: column; gap: 4px; }
    .kairo-rail-foot { margin-top: auto; padding-top: 24px; }

    .kairo-main {
      flex: 1; min-width: 0;
      padding: 52px 44px 130px; display: flex; justify-content: center;
    }
    .kairo-col { width: 100%; max-width: 1200px; }

    @media (max-width: 900px) {
      .kairo-app { flex-direction: column; }
      .kairo-rail {
        width: auto; height: auto; flex-direction: row; align-items: center;
        gap: 6px; padding: 12px 18px; z-index: 30;
        border-right: none; border-bottom: 1px solid var(--hairline);
        background: color-mix(in oklch, var(--paper) 80%, var(--surface));
        backdrop-filter: blur(8px);
      }
      .kairo-logo { padding: 0 14px 0 2px !important; }
      .kairo-navitems { flex-direction: row; margin-left: auto; gap: 4px; }
      .kairo-rail-foot { display: none; }
      .kairo-main { padding: 30px 18px 110px; }
    }
    @media (max-width: 520px) {
      .kairo-navitems button span:last-child { }
    }"""

    # ── JSX files (read at call-time so they're always current) ─────────────
    def _read(path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return fh.read()
        except Exception as exc:
            logger.error("Could not read %s: %s", path, exc)
            return f"/* ERROR reading {path}: {exc} */"

    base = str(Path(__file__).resolve().parent / "frontend")
    tweaks_panel_jsx     = _read(f"{base}/tweaks-panel.jsx")
    components_jsx       = _read(f"{base}/components.jsx")
    screen_morning_jsx   = _read(f"{base}/screen-morning.jsx")
    screen_narrative_jsx = _read(f"{base}/screen-narrative.jsx")
    screen_history_jsx   = _read(f"{base}/screen-history.jsx")
    screen_config_jsx    = _read(f"{base}/screen-config.jsx")
    screen_markets_jsx   = _read(f"{base}/screen-markets.jsx")
    app_jsx              = _read(f"{base}/app.jsx")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Kairo — Morning Brief</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&family=Mulish:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>
{styles_css}
{layout_css}
  </style>
</head>
<body>
  <div id="root"></div>
  <script>window.KAIRO = {data_json};</script>
  <script src="https://unpkg.com/react@18.3.1/umd/react.development.js" crossorigin="anonymous"></script>
  <script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.development.js" crossorigin="anonymous"></script>
  <script src="https://unpkg.com/@babel/standalone@7.29.0/babel.min.js" crossorigin="anonymous"></script>
  <script type="text/babel">
{tweaks_panel_jsx}
  </script>
  <script type="text/babel">
{components_jsx}
  </script>
  <script type="text/babel">
{screen_morning_jsx}
  </script>
  <script type="text/babel">
{screen_narrative_jsx}
  </script>
  <script type="text/babel">
{screen_history_jsx}
  </script>
  <script type="text/babel">
{screen_config_jsx}
  </script>
  <script type="text/babel">
{screen_markets_jsx}
  </script>
  <script type="text/babel">
{app_jsx}
  </script>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# JSON encoder that handles datetime objects safely
# ---------------------------------------------------------------------------

class _KairoEncoder(json.JSONEncoder):
    def default(self, obj): # type: ignore
        if isinstance(obj, datetime):
            return obj.isoformat()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

from config.config import Config as _Cfg

# ---------------------------------------------------------------------------
# Auth — user manager (cached for the session)
# ---------------------------------------------------------------------------

@st.cache_resource
def _get_user_manager():
    """Return a UserManager connected to MongoDB, or None if MONGO_URI not set."""
    import os as _os
    def _secret(key: str, default: str = "") -> str:
        try:
            return st.secrets.get(key, _os.getenv(key, getattr(_Cfg, key, default) or default))
        except Exception:
            return _os.getenv(key, getattr(_Cfg, key, default) or default)

    mongo_uri = _secret("MONGO_URI")
    mongo_db  = _secret("MONGO_DB") or "kairo"
    if not mongo_uri:
        return None
    try:
        from app.auth.user_manager import UserManager
        mgr = UserManager(mongo_uri, mongo_db)
        created = mgr.ensure_default_admin()
        if created:
            logger.info("Default admin account created (admin / kairo-admin). Change this password!")
        return mgr
    except Exception as exc:
        logger.warning("UserManager init failed: %s", exc)
        return None


_LOGIN_CSS = """
<style>
.auth-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--paper);
}
.auth-card {
  width: 100%;
  max-width: 400px;
  background: var(--surface);
  border: 1px solid var(--hairline);
  border-radius: var(--r-xl);
  box-shadow: var(--shadow-card);
  padding: 44px 40px 40px;
}
.auth-logo {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 32px;
}
.auth-logo-dot {
  width: 30px; height: 30px;
  border-radius: 9px;
  background: var(--ink);
  display: grid;
  place-items: center;
}
.auth-logo-inner {
  width: 13px; height: 13px;
  border-radius: 99px;
  background: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in oklch, var(--accent) 30%, transparent);
}
.auth-logo-text {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: -0.03em;
  color: var(--ink);
}
.auth-tagline {
  font-size: 13px;
  color: var(--ink-3);
  margin-top: -26px;
  margin-bottom: 32px;
}
</style>
"""


def _render_login_page(mgr) -> None:
    """Show the Kairo login/register gate. Blocks the rest of the app via st.stop()."""
    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    _, col, _ = st.columns([1, 1.4, 1])
    with col:
        st.markdown("""
        <div class="auth-logo">
          <div class="auth-logo-dot"><div class="auth-logo-inner"></div></div>
          <span class="auth-logo-text">Kairo</span>
        </div>
        <p class="auth-tagline">Understanding, not data.</p>
        """, unsafe_allow_html=True)

        if mgr is None:
            st.error("MongoDB not configured — authentication unavailable. Set MONGO_URI to enable login.")
            st.stop()

        sign_in_tab, register_tab = st.tabs(["Sign In", "Create Account"])

        with sign_in_tab:
            with st.form("login_form", clear_on_submit=False):
                username = st.text_input("Username", placeholder="your username")
                password = st.text_input("Password", type="password", placeholder="••••••••")
                submitted = st.form_submit_button("Sign In", use_container_width=True)

            if submitted:
                if not username or not password:
                    st.error("Please enter both username and password.")
                else:
                    user = mgr.authenticate(username, password)
                    if user:
                        st.session_state["_kairo_user"] = user
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")

            st.markdown(
                '<p style="font-size:12.5px;color:var(--ink-4);margin-top:8px;text-align:center">'
                'Default admin: <code>admin</code> / <code>kairo-admin</code></p>',
                unsafe_allow_html=True,
            )

        with register_tab:
            with st.form("register_form", clear_on_submit=True):
                new_user = st.text_input("Username", placeholder="choose a username", key="reg_user")
                new_pass = st.text_input("Password", type="password", placeholder="at least 8 characters", key="reg_pass")
                new_pass2 = st.text_input("Confirm password", type="password", placeholder="repeat password", key="reg_pass2")
                reg_submitted = st.form_submit_button("Create Account", use_container_width=True)

            if reg_submitted:
                if not new_user or not new_pass:
                    st.error("Username and password are required.")
                elif len(new_pass) < 8:
                    st.error("Password must be at least 8 characters.")
                elif new_pass != new_pass2:
                    st.error("Passwords do not match.")
                else:
                    ok = mgr.create_user(new_user, new_pass, role="user")
                    if ok:
                        st.success(f"Account created! You can now sign in as **{new_user.strip().lower()}**.")
                    else:
                        st.error(f"Username **{new_user.strip().lower()}** is already taken.")

    st.stop()


def _render_user_header(user: dict) -> None:
    """Render a slim logged-in banner at the top of the page."""
    role_badge_color = "var(--accent)" if user["role"] == "admin" else "var(--ink-3)"
    st.markdown(
        f"""
        <div style="
          display:flex; align-items:center; gap:10px;
          padding:8px 24px; background:var(--surface);
          border-bottom:1px solid var(--hairline);
          font-family:var(--font-sans); font-size:13px; color:var(--ink-3);
        ">
          <span>Signed in as <strong style="color:var(--ink)">{user["username"]}</strong></span>
          <span style="
            background:{role_badge_color}; color:var(--paper);
            font-size:10px; font-weight:700; letter-spacing:0.06em;
            text-transform:uppercase; padding:2px 8px; border-radius:99px;
          ">{user["role"]}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


if _Cfg.INGESTION_PROVIDER == "dune":
    from app.ingestion.dune_pipeline import build_pipeline as _build_pipeline
else:
    from app.ingestion.defillama_pipeline import build_defillama_pipeline as _build_pipeline

# ---------------------------------------------------------------------------
# Fragment: entire admin panel.
# Wrapping everything in ONE fragment means no interaction inside the admin
# tab ever causes a full-page re-run — the Kairo iframe is never touched.
# Only explicit st.rerun() calls (after data-changing operations) refresh
# the whole page so the Kairo tab picks up new data.
# ---------------------------------------------------------------------------

@st.fragment
def _admin_panel() -> None:
    _es, _engine, _tracker = init_services()
    col, _ = st.columns([5, 2])
    with col:
        _admin_panel_content(_es, _engine, _tracker)


def _run_narrative_backfill_flow(
    _es, _engine, _tracker, user_id: str,
    backfill_days: int, sleep_between: int, dry_run: bool = False,
) -> None:
    """Backfill narrative generation in weekly 168-h chunks, oldest first.
    Each window's output is chained as prior context to the next to prevent duplicates."""
    import time as _time
    from app.synthesize.signal_transformer import run_narrative_generation

    if _es is None or _engine is None:
        st.info("Services not fully configured.")
        return

    chunk_hours = 168
    total_hours = backfill_days * 24
    windows     = list(range(total_hours, 0, -chunk_hours)) or [total_hours]
    n           = len(windows)

    status   = st.empty()
    progress = st.progress(0, text=f"Narrative backfill — {n} weekly window(s)…")

    total_saved      = 0
    prior_narratives = None

    for i, w_hours in enumerate(windows, 1):
        weeks_ago = w_hours // 168
        label     = f"Window {i}/{n} — ~{weeks_ago}w lookback ({w_hours}h)"
        progress.progress(int(100 * (i - 1) / n), text=f"{label}…")

        if dry_run:
            status.info(f"[Dry run] {label}")
            _time.sleep(0.1)
            continue

        try:
            result = run_narrative_generation(
                hours=w_hours,
                user_id=user_id,
                es_manager=_es,
                engine=_engine,
                tracker=_tracker,
                dry_run=False,
                prior_narratives=prior_narratives,
            )
            total_saved     += len(result)
            prior_narratives = result if result else prior_narratives
            logger.info("[BACKFILL-UI] Window %d/%d done — %d narratives", i, n, len(result))
        except Exception as exc:
            st.warning(f"Window {i}/{n} ({w_hours}h) failed: {exc}")
            logger.exception("Backfill window %d failed", i)

        if i < n and sleep_between > 0:
            progress.progress(
                int(100 * (i - 1) / n),
                text=f"{label} — sleeping {sleep_between}s…",
            )
            _time.sleep(sleep_between)

    _cached_build_data.clear()
    progress.progress(100, text="Done.")
    if dry_run:
        status.info(f"Dry run complete — {n} window(s) previewed, no Gemini calls made.")
    else:
        status.success(f"Backfill complete — {total_saved} narrative(s) saved across {n} window(s).")
        st.rerun()


def _run_detection_flow(_es, _engine, _tracker, user_id: str, hours: int) -> None:
    """Shared detection logic used by both the standalone button and post-ingestion flow."""
    from app.synthesize.signal_transformer import SignalTransformer, enrich_with_acceleration
    from datetime import timezone as _tz

    if _es is None or _engine is None:
        st.info("Services not fully configured.")
        return

    status   = st.empty()
    progress = st.progress(0, text="Building unified signals…")
    try:
        progress.progress(10, text="Building unified signal schema…")
        _transformer    = SignalTransformer(_es)
        unified_signals = _transformer.build_unified_signals(hours=hours)
        unified_signals = enrich_with_acceleration(unified_signals, _es)
        logger.info(
            "[DETECT] Unified signals: %d records (%d capital_migration, %d smart_deployment, %d stablecoin_flow)",
            len(unified_signals),
            sum(1 for s in unified_signals if s["category"] == "capital_migration"),
            sum(1 for s in unified_signals if s["category"] == "smart_deployment"),
            sum(1 for s in unified_signals if s["category"] == "stablecoin_flow"),
        )

        progress.progress(25, text="Fetching Elasticsearch context…")
        dune_context = _es.get_dune_signal_context(hours=hours)

        progress.progress(35, text="Loading existing narratives from MongoDB…")
        current_narratives = _tracker.get_current_narratives(user_id, min_confidence=0.0) if _tracker else []
        history_summary    = _tracker.get_narratives_summary(user_id) if _tracker else []

        # Idempotency guard — block re-runs on same data window to prevent narrative drift.
        _signal_window_end = max(
            (s["time_bucket"] for s in unified_signals if s.get("time_bucket")),
            default=None,
        )
        if _signal_window_end and history_summary:
            _last_processed_end = None
            for _n in history_summary:
                _wend = _n.get("data_window_end")
                if _wend:
                    _wend_str = (
                        _wend.strftime("%Y-%m-%d")
                        if hasattr(_wend, "strftime")
                        else str(_wend)[:10]
                    )
                    if _last_processed_end is None or _wend_str > _last_processed_end:
                        _last_processed_end = _wend_str
            if _last_processed_end and _last_processed_end >= str(_signal_window_end):
                progress.empty()
                st.warning(
                    f"⚠️ Detection already ran for data window ending **{_last_processed_end}** "
                    f"(current signals also end at **{_signal_window_end}**). "
                    "Re-running on the same window causes narrative drift. "
                    "Fetch newer data or purge narratives first."
                )
                return

        progress.progress(50, text="Running Gemini narrative detection…")
        new_narratives = _engine.detect_narratives(
            dune_context=dune_context,
            historical_narratives=history_summary,
            unified_signals=unified_signals,
        )

        enriched = []
        if new_narratives:
            for i, n in enumerate(new_narratives):
                pct = 60 + int(30 * (i + 1) / len(new_narratives))
                progress.progress(pct, text=f"Enriching narrative {i + 1}/{len(new_narratives)}…")
                enriched.append(_engine.enrich_narrative(n, previous_narratives=current_narratives))

            _signal_meta = {
                "window_hours":  hours,
                "generated_at":  datetime.now(_tz.utc).isoformat(),
                "total_records": len(unified_signals),
                "by_category": {
                    "capital_migration": sum(1 for s in unified_signals if s["category"] == "capital_migration"),
                    "smart_deployment":  sum(1 for s in unified_signals if s["category"] == "smart_deployment"),
                    "stablecoin_flow":   sum(1 for s in unified_signals if s["category"] == "stablecoin_flow"),
                },
            }
            for n in enriched:
                n["unified_signals"] = unified_signals
                n["signal_metadata"] = _signal_meta

            if _tracker:
                progress.progress(92, text="Saving to MongoDB…")
                _tracker.save_narratives(enriched, user_id)
                returned_ids = {n.get("narrative_id") for n in enriched}
                _tracker.mark_stale_narratives(returned_ids, user_id)

        _cached_build_data.clear()
        progress.progress(100, text="Done.")
        count = len(new_narratives) if new_narratives else 0
        status.success(
            f"Detection complete — {count} narrative(s) detected. "
            "Switch to the Kairo tab to see results."
        )
        st.rerun()
    except Exception as exc:
        progress.empty()
        st.error(f"Detection error: {exc}")
        logger.exception("Detection failed")


def _admin_panel_content(_es, _engine, _tracker) -> None:
    from datetime import date as _date, timedelta as _td

    st.text_input("User ID", value="default", key="admin_user_id")
    _user_id = st.session_state.get("admin_user_id", "default")

    st.divider()

    # ── 1. Fetch On-Chain Data ─────────────────────────────────────────────────
    st.subheader("Fetch On-Chain Data")
    st.caption("Ingest historical on-chain data from Dune into Elasticsearch. Up to 6 months back.")

    _today         = _date.today()
    _max_backfill  = _today - _td(days=180)   # 6-month hard cap
    _fcol1, _fcol2 = st.columns(2)
    with _fcol1:
        _start_date = st.date_input(
            "From (UTC)",
            value=_today - _td(days=30),
            min_value=_max_backfill,
            max_value=_today,
            key="fetch_start_date",
            help="Earliest supported: 6 months back.",
        )
    with _fcol2:
        _end_date = st.date_input(
            "To (UTC)", value=_today, min_value=_max_backfill, max_value=_today, key="fetch_end_date"
        )

    _fetch_valid = bool(_start_date and _end_date and _end_date > _start_date)
    if _fetch_valid:
        _delta_days  = (_end_date - _start_date).days
        _delta_hours = _delta_days * 24
        _backfill_mode = _delta_days >= 7
        if _backfill_mode:
            _n_chunks = (_delta_days + 6) // 7
            st.caption(f"📦 Backfill mode — {_delta_days} days → {_n_chunks} weekly chunk(s)")
        else:
            st.caption(f"⚡ Direct query — {_delta_hours} hours")
    elif _start_date and _end_date:
        st.warning("End date must be after start date.")
        _delta_hours = 0
        _backfill_mode = False
    else:
        _delta_hours = 0
        _backfill_mode = False

    _run_detect_after = st.checkbox(
        "Also run narrative detection after ingestion",
        value=False,
        key="fetch_run_detect",
    )

    if st.button("Fetch Data", use_container_width=True, key="btn_fetch_data",
                 disabled=not _fetch_valid):
        _start_dt = datetime(_start_date.year, _start_date.month, _start_date.day, tzinfo=timezone.utc)
        _end_dt   = datetime(_end_date.year,   _end_date.month,   _end_date.day,
                             hour=23, minute=59, second=59, tzinfo=timezone.utc)
        try:
            _pipeline = _build_pipeline()
        except Exception as exc:
            st.error(f"Pipeline init failed: {exc}")
            logger.exception("Pipeline init failed")
            return

        _total_rows    = 0
        _total_indexed = 0
        _all_errors: list[str] = []

        if _backfill_mode:
            # Chunked: iterate weekly slices from start → end
            _cursor = _start_dt
            _chunks: list[tuple[datetime, datetime]] = []
            while _cursor < _end_dt:
                _ce = min(_cursor + _td(days=7), _end_dt)
                _chunks.append((_cursor, _ce))
                _cursor = _ce

            _prog = st.progress(0, text=f"Chunk 1/{len(_chunks)}…")
            _stat = st.empty()
            for _i, (_cs, _ce) in enumerate(_chunks):
                _end_str = _ce.strftime("%Y-%m-%d %H:%M:%S")
                _prog.progress(
                    int(100 * _i / len(_chunks)),
                    text=f"Chunk {_i + 1}/{len(_chunks)}: {_cs.date()} → {_ce.date()}",
                )
                try:
                    _res = _pipeline.run_all(
                        end_time=_end_str,
                        time_window_hours=168,
                    )
                    _total_rows    += sum(r.rows_fetched  for r in _res.values())
                    _total_indexed += sum(r.docs_indexed  for r in _res.values())
                    _all_errors.extend(
                        f"[{r.query_name}] chunk {_i + 1}: {r.error}"
                        for r in _res.values() if r.error
                    )
                except Exception as exc:
                    _all_errors.append(f"Chunk {_i + 1}: {exc}")
                    logger.exception("Backfill chunk %d failed", _i + 1)

            _prog.progress(100, text="Done.")
        else:
            # Single direct query
            _prog = st.progress(0, text=f"Running {_Cfg.INGESTION_PROVIDER} pipeline…")
            _stat = st.empty()
            _end_str = _end_dt.strftime("%Y-%m-%d %H:%M:%S")
            try:
                _prog.progress(20, text="Fetching on-chain data…")
                _res = _pipeline.run_all(
                    end_time=_end_str,
                    time_window_hours=_delta_hours,
                )
                _total_rows    = sum(r.rows_fetched  for r in _res.values())
                _total_indexed = sum(r.docs_indexed  for r in _res.values())
                _all_errors.extend(
                    f"[{r.query_name}] {r.error}" for r in _res.values() if r.error
                )
                _prog.progress(100, text="Done.")
            except Exception as exc:
                _prog.empty()
                st.error(f"Ingestion failed: {exc}")
                logger.exception("Ingestion failed")
                return

        _cached_build_data.clear()
        if _all_errors:
            _stat.warning(
                f"Ingested {_total_rows:,} rows ({_total_indexed:,} indexed) with {len(_all_errors)} error(s): "
                + "; ".join(_all_errors[:3])
            )
        else:
            _stat.success(f"Ingested {_total_rows:,} rows, {_total_indexed:,} docs indexed.")

        if _run_detect_after:
            st.markdown("---")
            st.markdown("**Running detection on fetched data…**")
            _detect_h = _delta_hours if not _backfill_mode else (_delta_days * 24 + 24)
            _run_detection_flow(_es, _engine, _tracker, _user_id, hours=max(_detect_h, 48))
        else:
            st.rerun()

    st.divider()

    # ── 2. Narrative Detection ────────────────────────────────────────────────
    st.subheader("Narrative Detection")
    st.caption("Runs Gemini detection on data currently in Elasticsearch.")

    _detect_hours = st.number_input(
        "Lookback window (hours)",
        min_value=1,
        max_value=8760,
        value=2160,
        step=24,
        key="detect_hours_input",
        help="2160 = 90 days. Use a large value to include all backfilled data.",
    )

    if st.button("🔮 Run Detection", use_container_width=True, key="btn_run_detection"):
        _run_detection_flow(_es, _engine, _tracker, _user_id, hours=int(_detect_hours))

    st.divider()

    # ── 2b. Narrative Backfill ─────────────────────────────────────────────────
    st.subheader("Narrative Backfill")
    st.caption(
        "Generates narratives in **weekly chunks** going back up to 6 months. "
        "Each week's output is automatically passed to the next as context — "
        "preventing Gemini from recreating the same narratives across windows."
    )

    _today_bf      = _date.today()
    _bf_min_date   = _today_bf - _td(days=180)
    _bf_presets    = {"2 weeks": 14, "1 month": 30, "3 months": 90, "6 months": 180}

    _bf_preset_col, _bf_custom_col = st.columns([2, 3])
    with _bf_preset_col:
        _bf_preset = st.selectbox(
            "Quick preset",
            options=list(_bf_presets.keys()),
            index=1,
            key="bf_preset",
        )
    with _bf_custom_col:
        _bf_start = st.date_input(
            "Or custom start date (UTC)",
            value=_today_bf - _td(days=_bf_presets[_bf_preset]),
            min_value=_bf_min_date,
            max_value=_today_bf - _td(days=1),
            key="bf_start_date",
            help="Earliest: 6 months back. Narratives are generated from this date to today.",
        )

    _bf_days  = (_today_bf - _bf_start).days if _bf_start else 30
    _bf_days  = max(1, min(_bf_days, 180))   # clamp to 6-month limit
    _bf_weeks = (_bf_days + 6) // 7
    st.caption(f"📦 {_bf_days} days → **{_bf_weeks} weekly Gemini call(s)**  ·  ~{_bf_weeks * 15}s minimum run time")

    _bf_col1, _bf_col2 = st.columns(2)
    with _bf_col1:
        _bf_sleep = st.number_input(
            "Sleep between calls (s)",
            min_value=5, max_value=120, value=15, step=5,
            key="bf_sleep_between",
            help="Pause between Gemini calls. Default 15s keeps you under the 10 RPM free-tier limit.",
        )
    with _bf_col2:
        _bf_dry_run = st.checkbox(
            "Dry run (preview windows, no Gemini calls)",
            value=False,
            key="bf_dry_run",
        )

    if st.button("📅 Run Narrative Backfill", use_container_width=True, key="btn_narrative_backfill"):
        _run_narrative_backfill_flow(
            _es, _engine, _tracker, _user_id,
            backfill_days=_bf_days,
            sleep_between=int(_bf_sleep),
            dry_run=_bf_dry_run,
        )

    st.divider()

    # ── 3. Purge Narratives ───────────────────────────────────────────────────
    st.subheader("Purge Narratives")
    st.caption(f"Permanently delete all narratives for user **{_user_id}** from MongoDB.")

    if not st.session_state.get("confirm_purge_pending"):
        if st.button("🗑 Purge Narratives", use_container_width=True,
                     key="btn_purge_start", type="secondary"):
            st.session_state["confirm_purge_pending"] = True
            st.rerun()
    else:
        st.warning(
            f"This will permanently delete **all narratives** for user `{_user_id}`. "
            "This cannot be undone."
        )
        _pc1, _pc2 = st.columns(2)
        with _pc1:
            if st.button("✅ Confirm Purge", use_container_width=True,
                         key="btn_purge_confirm", type="primary"):
                if _tracker:
                    _n_deleted = _tracker.purge_narratives(_user_id)
                    st.session_state.pop("confirm_purge_pending", None)
                    _cached_build_data.clear()
                    st.success(f"Deleted {_n_deleted} narrative(s).")
                    st.rerun()
                else:
                    st.error("MongoDB tracker not connected.")
        with _pc2:
            if st.button("Cancel", use_container_width=True, key="btn_purge_cancel"):
                st.session_state.pop("confirm_purge_pending", None)
                st.rerun()

    st.divider()

    # ── 4. Markets Update ─────────────────────────────────────────────────────
    st.subheader("Markets Data (Top 20)")
    st.caption("Fetches top 20 by market cap from CoinMarketCap and stores in MongoDB.")

    _cmc_key = st.text_input(
        "CoinMarketCap API Key",
        value=_Cfg.CMC_API_KEY or "",
        type="password",
        key="admin_cmc_key",
        help="Free key from coinmarketcap.com/api/  —  stored only in session, not saved to disk.",
    )
    _no_roadmap = st.checkbox(
        "Skip roadmap discovery (faster, website links only)",
        value=False,
        key="markets_skip_roadmap",
    )

    if st.button("🔄 Refresh Markets Data", use_container_width=True, key="btn_refresh_markets"):
        _key = _cmc_key or _Cfg.CMC_API_KEY
        if not _key:
            st.error("CMC_API_KEY required. Get a free key at coinmarketcap.com/api/ and add it above.")
        else:
            import os as _os
            _mongo_uri = _os.getenv("MONGO_URI") or _Cfg.MONGO_URI
            _mongo_db  = _os.getenv("MONGO_DB")  or _Cfg.MONGO_DB or "kairo"
            _mkt_prog = st.progress(0, text="Fetching CoinMarketCap data…")
            try:
                from app.ingestion.crypto_markets import CryptoMarketsUpdater
                _mkt_prog.progress(20, text="Calling CoinMarketCap API…")
                _upd = CryptoMarketsUpdater(_key, _mongo_uri, _mongo_db)
                _mkt_prog.progress(40, text="Fetching listings + metadata…")
                _projects = _upd.build_projects(discover_roadmaps=not _no_roadmap)
                _mkt_prog.progress(85, text="Saving to MongoDB…")
                _upd.save_to_mongo(_projects)
                _cached_build_data.clear()
                _mkt_prog.progress(100, text="Done.")
                st.success(f"Updated {len(_projects)} projects. Switch to the Markets tab to view.")
                st.rerun()
            except Exception as _exc:
                _mkt_prog.empty()
                st.error(f"Markets update failed: {_exc}")
                logger.exception("Markets update failed")

    st.divider()

    # ── 5. AI Market Analysis (Gemini) ────────────────────────────────────────
    st.subheader("AI Market Analysis")
    st.caption(
        "Uses Gemini to generate plain-English project summaries, ecosystem categories, "
        "traditional finance analogies, and roadmap summaries for each top-20 project. "
        "Run this after **Refresh Markets Data** above."
    )

    _ai_fast = st.checkbox(
        "Fast mode — skip roadmap page fetching (use Gemini knowledge only)",
        value=False,
        key="analysis_fast_mode",
        help="Fetching roadmap pages adds ~10s for the batch but gives Gemini real content to summarise.",
    )
    _ai_symbols_raw = st.text_input(
        "Limit to specific symbols (optional)",
        value="",
        placeholder="e.g. BTC ETH SOL — leave blank to analyse all 20",
        key="analysis_symbols",
    )

    if st.button("🤖 Run AI Market Analysis", use_container_width=True, key="btn_run_analysis"):
        import os as _os
        _mongo_uri = _os.getenv("MONGO_URI") or _Cfg.MONGO_URI
        _mongo_db  = _os.getenv("MONGO_DB")  or _Cfg.MONGO_DB or "kairo"

        _ai_prog    = st.progress(0, text="Initialising Gemini…")
        _ai_status  = st.empty()
        _ai_details = st.empty()

        try:
            from app.markets.analyzer import MarketAnalyzer

            _analyzer     = MarketAnalyzer(_mongo_uri, _mongo_db)
            _ai_symbols   = [s.strip().upper() for s in _ai_symbols_raw.split() if s.strip()] or None
            _fetch_roads  = not _ai_fast

            # Phase-1 progress: roadmap fetching (if enabled)
            if _fetch_roads:
                _ai_prog.progress(5, text="Fetching roadmap pages in parallel…")

            # We run analysis in a loop and update progress via callback
            _results_container: list = []
            _total_est = len(_ai_symbols) if _ai_symbols else 20

            def _progress_cb(current, total, name):
                pct  = int(5 + 90 * current / total)
                _ai_prog.progress(pct, text=f"Analysed {name} ({current}/{total})…")
                _results_container.append(name)

            _results = _analyzer.analyze_all(
                symbols=_ai_symbols,
                fetch_pages=_fetch_roads,
                dry_run=False,
                progress_cb=_progress_cb,
            )

            _ok    = sum(1 for r in _results if not r.get("analysis_error"))
            _errs  = sum(1 for r in _results if     r.get("analysis_error"))
            _cached_build_data.clear()
            _ai_prog.progress(100, text="Done.")

            if _errs:
                _ai_status.warning(
                    f"Analysis complete — {_ok}/{len(_results)} projects OK, {_errs} had errors. "
                    "Switch to the Markets tab to review."
                )
            else:
                _ai_status.success(
                    f"AI analysis complete — {_ok} projects analysed. "
                    "Switch to the Markets tab to see summaries, TradFi analogies, and roadmap breakdowns."
                )
            st.rerun()

        except ValueError as _exc:
            _ai_prog.empty()
            _ai_status.error(f"{_exc}")
        except Exception as _exc:
            _ai_prog.empty()
            _ai_status.error(f"Analysis failed: {_exc}")
            logger.exception("AI market analysis failed")

    st.divider()

    # ── 6. Service Status ─────────────────────────────────────────────────────
    st.subheader("Service Status")
    st.write("Elasticsearch:",    "✅ connected" if _es      is not None else "❌ not connected")
    st.write("Narrative Engine:", "✅ ready"     if _engine  is not None else "❌ not ready")
    st.write("MongoDB Tracker:",  "✅ connected" if _tracker is not None else "❌ not connected")


def run() -> None:
    """Entry point called by streamlit_app.py on every Streamlit rerun."""
    st.set_page_config(
        page_title="Kairo",
        page_icon="🔮",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

        /* ── Kairo design tokens (mirrors the React app) ── */
        :root {
          --paper:       oklch(0.985 0.006 80);
          --surface:     oklch(0.995 0.004 85);
          --surface-2:   oklch(0.965 0.008 80);
          --hairline:    oklch(0.90  0.010 75);
          --hairline-strong: oklch(0.84 0.012 70);
          --ink:         oklch(0.27  0.012 60);
          --ink-2:       oklch(0.42  0.012 60);
          --ink-3:       oklch(0.58  0.012 65);
          --ink-4:       oklch(0.70  0.010 70);
          --accent:      oklch(0.64  0.124 42);
          --accent-soft: oklch(0.92  0.045 50);
          --accent-ink:  oklch(0.46  0.115 40);
          --font-sans:   "Hanken Grotesk", ui-sans-serif, system-ui, sans-serif;
          --font-mono:   "IBM Plex Mono", ui-monospace, monospace;
          --r-sm: 10px; --r-md: 16px; --r-lg: 22px;
          --shadow-card: 0 1px 2px oklch(0.5 0.02 60 / 0.05), 0 6px 22px oklch(0.5 0.02 60 / 0.06);
        }

        /* ── Chrome / chrome resets ── */
        #MainMenu, header, footer { display: none !important; }
        .stApp { padding: 0 !important; background: var(--paper) !important; }
        .block-container { padding: 0 !important; max-width: 100% !important; }
        div[data-testid="stVerticalBlock"] { gap: 0 !important; }
        iframe { border: none !important; }

        /* ── Global font ── */
        .stApp, .stApp * {
          font-family: var(--font-sans) !important;
          -webkit-font-smoothing: antialiased;
        }

        /* ── Tabs ── */
        .stTabs [data-baseweb="tab-list"] {
          background: var(--surface) !important;
          border-bottom: 1px solid var(--hairline) !important;
          gap: 0 !important;
          padding: 0 28px !important;
        }
        .stTabs [data-baseweb="tab"] {
          font-weight: 600 !important;
          font-size: 14px !important;
          color: var(--ink-3) !important;
          border-bottom: 2px solid transparent !important;
          padding: 14px 18px !important;
          background: transparent !important;
        }
        .stTabs [aria-selected="true"] {
          color: var(--ink) !important;
          border-bottom-color: var(--accent) !important;
        }
        .stTabs [data-baseweb="tab-panel"] { padding: 0 !important; }

        /* ── Headings ── */
        [data-testid="stHeadingWithActionElements"] h2,
        [data-testid="stHeadingWithActionElements"] h3,
        .stMarkdown h2, .stMarkdown h3 {
          color: var(--ink) !important;
          font-weight: 700 !important;
          letter-spacing: -0.015em !important;
          margin-top: 4px !important;
        }

        /* ── Divider ── */
        hr { border-color: var(--hairline) !important; margin: 20px 0 !important; }

        /* ── Widget labels ── */
        [data-testid="stWidgetLabel"] p,
        .stSelectbox label, .stSlider label, .stTextInput label,
        .stCheckbox label, .stRadio label {
          font-weight: 600 !important;
          color: var(--ink-2) !important;
          font-size: 13.5px !important;
          letter-spacing: 0 !important;
        }

        /* ── Text input ── */
        .stTextInput input {
          background: var(--surface) !important;
          border: 1px solid var(--hairline-strong) !important;
          border-radius: var(--r-sm) !important;
          color: var(--ink) !important;
          font-size: 15px !important;
          padding: 10px 14px !important;
          box-shadow: none !important;
        }
        .stTextInput input:focus {
          border-color: var(--accent) !important;
          box-shadow: 0 0 0 3px var(--accent-soft) !important;
        }

        /* ── Selectbox ── */
        [data-baseweb="select"] > div:first-child {
          background: var(--surface) !important;
          border: 1px solid var(--hairline-strong) !important;
          border-radius: var(--r-sm) !important;
          color: var(--ink) !important;
          font-size: 15px !important;
        }
        [data-baseweb="popover"] [data-baseweb="menu"] {
          background: var(--surface) !important;
          border: 1px solid var(--hairline) !important;
          border-radius: var(--r-md) !important;
          box-shadow: var(--shadow-card) !important;
        }
        [data-baseweb="menu"] li {
          color: var(--ink-2) !important;
          font-size: 14.5px !important;
        }
        [data-baseweb="menu"] li:hover {
          background: var(--surface-2) !important;
        }

        /* ── Slider ── */
        [data-testid="stSlider"] [data-testid="stThumbValue"] {
          color: var(--ink) !important;
          font-weight: 700 !important;
          font-family: var(--font-mono) !important;
        }
        [data-testid="stSlider"] [role="slider"] {
          background: var(--accent) !important;
          border-color: var(--accent) !important;
        }
        [data-testid="stSlider"] [data-testid="stSliderTrack"] > div:first-child {
          background: var(--accent) !important;
        }

        /* ── Checkbox ── */
        .stCheckbox [data-testid="stCheckbox"] > label {
          color: var(--ink-2) !important;
        }
        .stCheckbox [data-testid="stCheckbox"] input:checked + div {
          background: var(--accent) !important;
          border-color: var(--accent) !important;
        }

        /* ── Buttons ── */
        .stButton > button {
          background: var(--accent) !important;
          color: var(--paper) !important;
          border: none !important;
          border-radius: var(--r-sm) !important;
          font-weight: 700 !important;
          font-size: 14.5px !important;
          padding: 11px 24px !important;
          letter-spacing: -0.01em !important;
          transition: background 0.15s !important;
          box-shadow: none !important;
        }
        .stButton > button:hover {
          background: var(--accent-ink) !important;
          color: var(--paper) !important;
        }
        .stButton > button:focus {
          box-shadow: 0 0 0 3px var(--accent-soft) !important;
          outline: none !important;
        }

        /* ── Caption ── */
        .stCaptionContainer p,
        [data-testid="stCaptionContainer"] p {
          color: var(--ink-3) !important;
          font-size: 13px !important;
        }

        /* ── Alerts ── */
        [data-testid="stAlert"] {
          border-radius: var(--r-md) !important;
          font-size: 14.5px !important;
        }

        /* ── Progress bar ── */
        [data-testid="stProgressBar"] > div {
          background: var(--accent-soft) !important;
          border-radius: 99px !important;
        }
        [data-testid="stProgressBar"] > div > div {
          background: var(--accent) !important;
          border-radius: 99px !important;
        }
        [data-testid="stProgressBar"] + div p {
          color: var(--ink-3) !important;
          font-size: 13px !important;
        }

        /* ── Write / text ── */
        .stMarkdown p, [data-testid="stText"] {
          color: var(--ink-2) !important;
          font-size: 14.5px !important;
        }

        /* ── Running indicator — keep visible but style it ── */
        [data-testid="stStatusWidget"] { opacity: 0.7 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    # ── Two-tab layout ────────────────────────────────────────────────────────
    tab_kairo, tab_admin = st.tabs(["Kairo", "⚙ Admin"])

    with tab_admin:
        _admin_panel()

    # ── Kairo tab — iframe only ───────────────────────────────────────────────
    with tab_kairo:
        user_id        = st.session_state.get("admin_user_id", "default")
        hours_lookback = int(st.session_state.get("detect_hours_input", _Cfg.DUNE_QUERY_WINDOW_HOURS))

        kairo_data = _cached_build_data(user_id, hours_lookback)
        kairo_data.setdefault("config", {})["dune_query_window_hours"] = _Cfg.DUNE_QUERY_WINDOW_HOURS

        try:
            data_json_str = json.dumps(kairo_data, cls=_KairoEncoder, ensure_ascii=False)
        except Exception as exc:
            logger.exception("JSON serialisation failed: %s", exc)
            from app.synthesize.kairo_data import _empty_data
            data_json_str = json.dumps(_empty_data(), ensure_ascii=False)

        html = build_kairo_html(data_json_str)
        st.components.v1.html(html, height=1400, scrolling=True)
