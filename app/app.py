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

@st.cache_resource(show_spinner=False)
def _get_concept_tracker():
    """Return a ConceptTracker connected to MongoDB, or None if MONGO_URI not set."""
    import os as _os
    def _s(key, default=""):
        try:
            return st.secrets.get(key, _os.getenv(key, default) or default)
        except Exception:
            return _os.getenv(key, default) or default

    mongo_uri = _s("MONGO_URI")
    mongo_db  = _s("MONGO_DB") or "kairo"
    if not mongo_uri:
        return None
    try:
        from app.education.concept_tracker import ConceptTracker
        return ConceptTracker(mongo_uri, mongo_db)
    except Exception as exc:
        logger.warning("ConceptTracker init failed: %s", exc)
        return None


@st.cache_resource
def _get_regulation_tracker():
    """Return a RegulationTracker connected to MongoDB, or None if MONGO_URI not set."""
    import os as _os
    def _s(key, default=""):
        try:
            return st.secrets.get(key, _os.getenv(key, default) or default)
        except Exception:
            return _os.getenv(key, default) or default

    mongo_uri = _s("MONGO_URI")
    mongo_db  = _s("MONGO_DB") or "kairo"
    if not mongo_uri:
        return None
    try:
        from app.regulations.regulation_tracker import RegulationTracker
        return RegulationTracker(mongo_uri, mongo_db)
    except Exception as exc:
        logger.warning("RegulationTracker init failed: %s", exc)
        return None


@st.cache_resource
def init_services():
    """Initialise ES, Gemini, and MongoDB. Returns (es_manager, narrative_engine, tracker).

    Service requirements (intentionally asymmetric):
      • MongoDB  — REQUIRED for the website to render briefs, regulations,
                   profile, and Crypto 101 content. Without it, the auth gate
                   blocks first anyway, so the user sees the login error.
      • ES       — OPTIONAL. Used only to enrich live data during ingestion
                   and detection. If down/misconfigured we render Mongo-backed
                   content and skip on-chain enrichment silently.
      • Gemini   — OPTIONAL. Used only during narrative detection / regulation
                   refresh. The site renders without it; admin actions that
                   need it will surface an error at that point.
    """
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

    # ES: optional. Failures are logged at info-level so they don't pollute
    # the admin log with red text on a perfectly working site.
    es_manager = None
    if es_url:
        try:
            es_manager = ElasticsearchManager(es_url, es_username, es_password, es_api_key_id)
        except Exception as exc:
            logger.info("ES unavailable — site will render without on-chain enrichment (%s).", exc)
    else:
        logger.info("ES_URL not configured — site will render without on-chain enrichment.")

    # Gemini: optional. Only needed for ingestion/detection admin flows.
    narrative_engine = None
    if gemini_key:
        try:
            narrative_engine = NarrativeEngine(gemini_key)
        except Exception as exc:
            logger.info("Gemini unavailable — admin AI flows disabled (%s).", exc)
    else:
        logger.info("GEMINI_KEY not configured — admin AI flows disabled.")

    # Mongo: required. We still don't raise — let the iframe handle empty
    # data — but log loudly so the operator notices.
    tracker = None
    if mongo_uri:
        try:
            tracker = NarrativeTracker(mongo_uri, mongo_db)
        except Exception as exc:
            logger.warning("NarrativeTracker init failed (MongoDB required): %s", exc)
    else:
        logger.warning("MONGO_URI not configured — MongoDB is required for Kairo to work.")

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
 #       if es_manager is not None:
 #           try:
 #               dune_context = es_manager.get_dune_signal_context(hours=hours)
 #           except Exception as exc:
 #               logger.warning("get_dune_signal_context failed: %s", exc)

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
  height: 100%;
  overflow: hidden;
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
    /* ── App shell: fixed viewport height, main content scrolls ── */
    .kairo-app { display: flex; height: 100vh; overflow: hidden; }

    .kairo-rail {
      width: 244px; flex-shrink: 0;
      height: 100vh; overflow-y: auto;
      padding: 26px 18px; display: flex; flex-direction: column;
      border-right: 1px solid var(--hairline);
      background: color-mix(in oklch, var(--paper) 60%, var(--surface));
    }
    .kairo-navitems { display: flex; flex-direction: column; gap: 4px; }
    .kairo-rail-foot { margin-top: auto; padding-top: 24px; }

    .kairo-main {
      flex: 1; min-width: 0;
      height: 100vh; overflow-y: auto;
      padding: 52px 44px 80px; display: flex; justify-content: center;
    }
    .kairo-col { width: 100%; max-width: 1200px; }

    @media (max-width: 640px) {
      .kairo-app { flex-direction: column; height: auto; overflow: visible; }
      .kairo-rail {
        width: auto; height: auto; overflow-y: visible;
        flex-direction: row; align-items: center;
        gap: 6px; padding: 12px 18px; z-index: 30;
        border-right: none; border-bottom: 1px solid var(--hairline);
        background: color-mix(in oklch, var(--paper) 80%, var(--surface));
        backdrop-filter: blur(8px);
        position: sticky; top: 0;
      }
      .kairo-logo { padding: 0 14px 0 2px !important; }
      .kairo-navitems { flex-direction: row; margin-left: auto; gap: 4px; }
      .kairo-rail-foot { display: none; }
      .kairo-main { height: auto; overflow-y: visible; padding: 30px 18px 60px; }
    }
    @media (max-width: 480px) {
      .kairo-navitems button span:last-child { display: none; }
    }

    /* ── Loading screen (replaced by React once mounted) ── */
    .kairo-loading {
      min-height: 100vh;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 18px;
      background: var(--paper);
      font-family: var(--font-sans);
    }
    .kairo-loading-logo {
      display: flex; align-items: center; gap: 11px; margin-bottom: 4px;
    }
    .kairo-loading-dot {
      width: 30px; height: 30px; border-radius: 9px;
      background: var(--ink); display: grid; place-items: center;
    }
    .kairo-loading-dot-inner {
      width: 13px; height: 13px; border-radius: 99px;
      background: var(--accent);
      animation: kairo-pulse 1.5s ease-in-out infinite;
    }
    .kairo-loading-text {
      font-size: 14.5px; color: var(--ink-3); letter-spacing: 0.01em;
    }
    @keyframes kairo-pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50%       { opacity: 0.4; transform: scale(0.78); }
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
    tweaks_panel_jsx       = _read(f"{base}/tweaks-panel.jsx")
    components_jsx         = _read(f"{base}/components.jsx")
    screen_morning_jsx     = _read(f"{base}/screen-morning.jsx")
    screen_narrative_jsx   = _read(f"{base}/screen-narrative.jsx")
    screen_history_jsx     = _read(f"{base}/screen-history.jsx")
    screen_config_jsx      = _read(f"{base}/screen-config.jsx")
    screen_markets_jsx     = _read(f"{base}/screen-markets.jsx")
    screen_profile_jsx     = _read(f"{base}/screen-profile.jsx")
    screen_regulations_jsx = _read(f"{base}/screen-regulations.jsx")
    screen_learn_jsx       = _read(f"{base}/screen-learn.jsx")
    app_jsx                = _read(f"{base}/app.jsx")

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
  <div id="root">
    <div class="kairo-loading">
      <div class="kairo-loading-logo">
        <div class="kairo-loading-dot"><div class="kairo-loading-dot-inner"></div></div>
        <span style="font-size:21px;font-weight:800;letter-spacing:-0.03em;color:var(--ink)">Kairo</span>
      </div>
      <div class="kairo-loading-text">Loading your news…</div>
    </div>
  </div>
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
{screen_profile_jsx}
  </script>
  <script type="text/babel">
{screen_regulations_jsx}
  </script>
  <script type="text/babel">
{screen_learn_jsx}
  </script>
  <script type="text/babel">
{app_jsx}
  </script>
  <script>
  /* Resize this iframe to fill the parent viewport so the app never clips
     and only the inner .kairo-main div scrolls (not an outer iframe bar). */
  (function () {{
    function fit() {{
      var h;
      try {{ h = window.parent.innerHeight; }} catch (e) {{ h = window.innerHeight || 900; }}
      /* Subtract ~56 px for Streamlit tab bar (admin view); 0 for plain user view.
         postMessage is safe on same-origin Streamlit deployments. */
      h = Math.max(h - 56, 600);
      try {{
        window.parent.postMessage({{
          isStreamlitMessage: true,
          type: "streamlit:setFrameHeight",
          args: {{ height: h }}
        }}, "*");
      }} catch (e) {{}}
    }}
    fit();
    window.addEventListener("resize", fit);
  }})();
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
        bootstrap = mgr.ensure_default_admin()
        if bootstrap:
            _u, _p = bootstrap
            logger.warning(
                "Bootstrap admin created — username=%s. One-time password printed once below. "
                "Sign in and change it immediately, then remove this account or rotate the password.",
                _u,
            )
            logger.warning("BOOTSTRAP ADMIN PASSWORD: %s", _p)
        return mgr
    except Exception as exc:
        logger.warning("UserManager init failed: %s", exc)
        return None


_LOGIN_CSS = """
<style>
/* ── Design tokens (mirrors the authenticated app's :root) ──────────── */
:root {
  --paper:    oklch(0.985 0.006 80);
  --surface:  oklch(0.995 0.004 85);
  --surface-2:oklch(0.965 0.008 80);
  --hairline: oklch(0.90 0.010 75);
  --hairline-strong: oklch(0.84 0.012 70);
  --ink:      oklch(0.27 0.012 60);
  --ink-2:    oklch(0.42 0.012 60);
  --ink-3:    oklch(0.58 0.012 65);
  --ink-4:    oklch(0.70 0.010 70);
  --accent:        oklch(0.64 0.124 42);
  --accent-soft:   oklch(0.92 0.045 50);
  --accent-ink:    oklch(0.46 0.115 40);
  --font-sans: "Hanken Grotesk", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SF Mono", monospace;
  --r-sm: 10px;
  --r-md: 16px;
  --r-lg: 22px;
  --r-xl: 28px;
  --shadow-card: 0 1px 2px oklch(0.5 0.02 60 / 0.05), 0 6px 22px oklch(0.5 0.02 60 / 0.06);
  --gap: 18px;
  --card-pad: 26px;
}

/* Hide Streamlit chrome on the login page */
#MainMenu, header, footer { display: none !important; }
.stApp { background: var(--paper) !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ── Real two-column layout via st.columns ───────────────────────────── */
/* Streamlit form widgets can't be parented to a div we open in markdown,
   so we use st.columns and apply pane styling to the columns themselves. */
.stApp [data-testid="stHorizontalBlock"]:first-of-type {
  gap: 0 !important;
  align-items: stretch !important;
  min-height: calc(100vh - 64px); /* leave room for footer */
}

/* Left pane (marketing) — first column gets the warm gradient + brand */
.stApp [data-testid="stHorizontalBlock"]:first-of-type > [data-testid="stColumn"]:first-child {
  background:
    radial-gradient(800px 400px at 12% 10%, color-mix(in oklch, var(--accent) 18%, transparent), transparent 60%),
    radial-gradient(700px 500px at 90% 90%, color-mix(in oklch, var(--accent) 10%, transparent), transparent 60%),
    var(--surface) !important;
  border-right: 1px solid var(--hairline);
  padding: 56px 56px 40px !important;
  display: flex;
  flex-direction: column;
}
.stApp [data-testid="stHorizontalBlock"]:first-of-type > [data-testid="stColumn"]:first-child
  > [data-testid="stVerticalBlock"] {
  height: 100%;
}

/* Right pane (form) — second column centers the auth card */
.stApp [data-testid="stHorizontalBlock"]:first-of-type > [data-testid="stColumn"]:last-child {
  background: var(--paper);
  padding: 56px 48px !important;
  display: flex;
  align-items: center;
}
.stApp [data-testid="stHorizontalBlock"]:first-of-type > [data-testid="stColumn"]:last-child
  > [data-testid="stVerticalBlock"] {
  max-width: 420px;
  margin: 0 auto;
  width: 100%;
}

@media (max-width: 960px) {
  .stApp [data-testid="stHorizontalBlock"]:first-of-type {
    flex-direction: column;
    min-height: auto;
  }
  .stApp [data-testid="stHorizontalBlock"]:first-of-type > [data-testid="stColumn"]:first-child {
    padding: 40px 28px !important;
    border-right: none;
    border-bottom: 1px solid var(--hairline);
  }
  .stApp [data-testid="stHorizontalBlock"]:first-of-type > [data-testid="stColumn"]:last-child {
    padding: 40px 28px !important;
  }
}

/* ── Left pane content ───────────────────────────────────────────────── */
.auth-hero-inner {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  flex: 1;
  gap: 40px;
}
.auth-brand { display: flex; align-items: center; gap: 12px; }
.auth-brand-dot {
  width: 34px; height: 34px; border-radius: 10px; background: var(--ink);
  display: grid; place-items: center;
}
.auth-brand-dot-inner {
  width: 14px; height: 14px; border-radius: 99px; background: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in oklch, var(--accent) 30%, transparent);
}
.auth-brand-text {
  font-size: 26px; font-weight: 800; letter-spacing: -0.03em; color: var(--ink);
}
.auth-hero-headline {
  font-size: 42px; line-height: 1.05; font-weight: 800;
  color: var(--ink); letter-spacing: -0.035em;
  margin: 0 0 18px; max-width: 540px;
}
.auth-hero-headline em {
  font-style: normal; color: var(--accent-ink);
  background: linear-gradient(120deg, var(--accent-soft) 0%, transparent 100%);
  padding: 0 4px;
}
.auth-hero-sub {
  font-size: 16.5px; line-height: 1.55; color: var(--ink-2);
  max-width: 500px; margin: 0 0 32px;
}
.auth-pills { display: flex; flex-direction: column; gap: 12px; max-width: 500px; }
.auth-pill {
  display: flex; align-items: flex-start; gap: 14px;
  padding: 14px 16px; background: var(--surface-2);
  border: 1px solid var(--hairline); border-radius: var(--r-md);
}
.auth-pill-mark {
  flex-shrink: 0; width: 28px; height: 28px; border-radius: 8px;
  background: var(--accent-soft); color: var(--accent-ink);
  display: grid; place-items: center; font-size: 14px; font-weight: 800;
}
.auth-pill-title {
  font-size: 14px; font-weight: 700; color: var(--ink);
  letter-spacing: -0.01em; margin: 0 0 2px;
}
.auth-pill-copy {
  font-size: 13px; line-height: 1.5; color: var(--ink-3); margin: 0;
}
.auth-tagline {
  font-size: 12px; color: var(--ink-4); letter-spacing: 0.02em;
  margin-top: 8px;
}

/* ── Right pane content ──────────────────────────────────────────────── */
.auth-card-head h2 {
  font-size: 24px; font-weight: 800; color: var(--ink);
  letter-spacing: -0.02em; margin: 0 0 8px;
}
.auth-card-head p {
  font-size: 14px; color: var(--ink-3); margin: 0 0 24px;
}
.stApp [data-testid="stHorizontalBlock"]:first-of-type
  [data-testid="stColumn"]:last-child .stTabs [data-baseweb="tab-list"] {
  background: transparent !important;
  border-bottom: 1px solid var(--hairline) !important;
  gap: 24px !important;
  padding: 0 !important;
  margin-bottom: 20px !important;
}
.stApp [data-testid="stHorizontalBlock"]:first-of-type
  [data-testid="stColumn"]:last-child .stTabs [data-baseweb="tab"] {
  padding: 10px 0 !important;
  font-size: 14px !important;
}
.auth-meta {
  font-size: 12px; color: var(--ink-4);
  margin-top: 16px; text-align: center; line-height: 1.5;
}

/* ── Bottom footer bar ───────────────────────────────────────────────── */
.auth-footer {
  border-top: 1px solid var(--hairline);
  background: var(--surface);
  padding: 14px 56px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12.5px;
  color: var(--ink-4);
}
.auth-footer-links {
  display: flex;
  gap: 22px;
  flex-wrap: wrap;
}
.auth-footer-links a {
  color: var(--ink-3);
  text-decoration: none;
  font-weight: 600;
  transition: color 0.15s;
}
.auth-footer-links a:hover { color: var(--ink); }

/* ── CSS-only modals (no rerun, no JS) ───────────────────────────────── */
/* Each modal is hidden until its anchor (#about, #terms, #privacy) is
   targeted by the URL hash. Clicking the link opens it; clicking the
   backdrop or close button (href="#close") clears the hash and hides it. */
.auth-modal {
  display: none;
  position: fixed;
  inset: 0;
  background: oklch(0.2 0.012 60 / 0.5);
  z-index: 9999;
  padding: 32px;
  overflow-y: auto;
}
.auth-modal:target {
  display: flex;
  align-items: flex-start;
  justify-content: center;
}
.auth-modal-backdrop {
  position: absolute;
  inset: 0;
  text-decoration: none;
  /* Click-through transparent link covering backdrop */
}
.auth-modal-card {
  position: relative;
  background: var(--paper);
  border: 1px solid var(--hairline);
  border-radius: var(--r-xl);
  box-shadow: 0 28px 70px oklch(0.25 0.02 60 / 0.22);
  width: 100%;
  max-width: 640px;
  margin: 6vh auto;
  padding: 44px 48px 36px;
}
.auth-modal-close {
  position: absolute;
  top: 16px; right: 16px;
  width: 34px; height: 34px;
  border-radius: 99px;
  background: var(--surface-2);
  color: var(--ink-2);
  text-decoration: none;
  display: grid;
  place-items: center;
  font-size: 22px;
  line-height: 1;
  font-weight: 500;
  transition: background 0.15s;
}
.auth-modal-close:hover { background: var(--hairline); color: var(--ink); }
.auth-modal-card h2 {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.025em;
  color: var(--ink);
  margin: 0 0 6px;
}
.auth-modal-card .modal-sub {
  font-size: 14px;
  color: var(--ink-3);
  margin: 0 0 24px;
}
.auth-modal-card h3 {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.10em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin: 22px 0 10px;
}
.auth-modal-card p {
  color: var(--ink-2);
  font-size: 14.5px;
  line-height: 1.65;
  margin: 0 0 12px;
}
.auth-modal-card ul {
  padding-left: 18px;
  color: var(--ink-2);
  font-size: 14.5px;
  line-height: 1.7;
  margin: 0 0 10px;
}
.auth-modal-card ul li { margin: 4px 0; }
.auth-modal-card ul li strong { color: var(--ink); }

/* ── Orange (Kairo-accent) primary buttons ────────────────────────── */
.auth-panel button[kind="primary"],
.auth-panel button[data-testid*="primary"] {
  background: var(--accent) !important;
  color: var(--paper) !important;
  border: none !important;
  font-weight: 700 !important;
}
.auth-panel button[kind="primary"]:hover,
.auth-panel button[data-testid*="primary"]:hover {
  background: var(--accent-ink) !important;
}

.auth-modal-card .modal-fineprint {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--hairline);
  font-size: 12.5px;
  color: var(--ink-4);
  line-height: 1.55;
}
</style>

<!-- Defense in depth: limit URL leakage if a remember-me token ends up in the address bar. -->
<meta name="referrer" content="strict-origin-when-cross-origin">
"""


# Marketing pane content (left column)
_AUTH_HERO_HTML = """
<div class="auth-hero-inner">
  <div class="auth-brand">
    <div class="auth-brand-dot"><div class="auth-brand-dot-inner"></div></div>
    <span class="auth-brand-text">Kairo</span>
  </div>

  <div>
    <h1 class="auth-hero-headline">
      Crypto intelligence, <em>built like an HNI desk</em> — for everyone.
    </h1>
    <p class="auth-hero-sub">
      Kairo decodes the signals the largest investors trade on — capital flows,
      narrative shifts, regulatory moves — and turns them into clear,
      plain-English briefs so you can act with conviction, not noise.
    </p>

    <div class="auth-pills">
      <div class="auth-pill">
        <div class="auth-pill-mark">⇡</div>
        <div>
          <p class="auth-pill-title">Live narrative signals</p>
          <p class="auth-pill-copy">Spot rotations the moment whales pivot — across L2s, AI, RWAs and more.</p>
        </div>
      </div>
      <div class="auth-pill">
        <div class="auth-pill-mark">◆</div>
        <div>
          <p class="auth-pill-title">Markets &amp; policy in one view</p>
          <p class="auth-pill-copy">Price action, regulation, and on-chain flow — synthesized, not stitched together.</p>
        </div>
      </div>
      <div class="auth-pill">
        <div class="auth-pill-mark">✶</div>
        <div>
          <p class="auth-pill-title">A daily brief that respects your time</p>
          <p class="auth-pill-copy">Wake up to a 3-minute read on what moved, why, and what it means for you.</p>
        </div>
      </div>
    </div>
  </div>

  <div class="auth-tagline">Understanding, not data.</div>
</div>
"""


# Footer bar + the three CSS-target modals (About Us, Terms, Privacy)
_AUTH_FOOTER_AND_MODALS = """
<div class="auth-footer">
  <span>© 2026 Kairo. All rights reserved.</span>
  <nav class="auth-footer-links" aria-label="Footer">
    <a href="#about">About Us</a>
    <a href="#terms">Terms &amp; Conditions</a>
    <a href="#privacy">Privacy</a>
  </nav>
</div>

<!-- About Us -->
<div id="about" class="auth-modal" role="dialog" aria-modal="true" aria-labelledby="about-title">
  <a class="auth-modal-backdrop" href="#close" aria-label="Close dialog"></a>
  <div class="auth-modal-card">
    <a class="auth-modal-close" href="#close" aria-label="Close">×</a>
    <h2 id="about-title">About Kairo</h2>
    <p class="modal-sub">Crypto intelligence, built like an HNI desk — for everyone.</p>

    <h3>Our Mission</h3>
    <p>
      Kairo exists to put the kind of market intelligence that high-net-worth
      and institutional desks rely on into the hands of every individual
      investor and curious learner. We decode capital flows, narrative shifts,
      and regulatory context so that digital currencies and assets become
      <strong>understandable</strong> and <strong>accessible</strong> — not
      reserved for the few.
    </p>

    <h3>Our Values</h3>
    <ul>
      <li><strong>Clarity over noise.</strong> We summarize, we don't stream. Every brief earns its place.</li>
      <li><strong>Education first.</strong> Every signal is explained, not just reported. We respect your time and your curiosity.</li>
      <li><strong>Privacy by default.</strong> Your data is yours. Sessions are encrypted, tokens are hashed at rest, and we never sell personal data.</li>
      <li><strong>Honest about limits.</strong> Briefs are research, not financial advice. We tell you what we see; you decide what to do.</li>
      <li><strong>Built for the curious.</strong> Whether you're new to crypto or running a portfolio, Kairo meets you where you are.</li>
    </ul>

    <p class="modal-fineprint">
      Kairo is an independent research tool. We are not registered as an
      investment advisor and do not provide personalized financial advice.
    </p>
  </div>
</div>

<!-- Terms &amp; Conditions -->
<div id="terms" class="auth-modal" role="dialog" aria-modal="true" aria-labelledby="terms-title">
  <a class="auth-modal-backdrop" href="#close" aria-label="Close dialog"></a>
  <div class="auth-modal-card">
    <a class="auth-modal-close" href="#close" aria-label="Close">×</a>
    <h2 id="terms-title">Terms &amp; Conditions</h2>
    <p class="modal-sub">Last updated: June 2026 · By using Kairo, you agree to the following.</p>

    <h3>1. Acceptance &amp; Eligibility</h3>
    <p>
      By creating an account or using Kairo, you confirm that you are at least
      18 years old and legally able to enter into this agreement. If you do
      not agree to these terms, do not use the service.
    </p>

    <h3>2. Educational Use Only</h3>
    <p>
      Kairo provides research, market commentary, and data summaries for
      <strong>educational and informational purposes only</strong>. Nothing in
      Kairo is financial, investment, tax, or legal advice, an offer to buy or
      sell any asset, or a solicitation of any kind. Always do your own
      research and consult a licensed professional before making decisions.
    </p>

    <h3>3. No Warranty on Data</h3>
    <p>
      Kairo aggregates data from third-party sources (on-chain providers,
      market data vendors, public regulatory feeds). We make reasonable efforts
      to ensure accuracy but make no guarantee. Use of any information is at
      your own risk.
    </p>

    <h3>4. Your Account</h3>
    <ul>
      <li>You are responsible for keeping your password secure and for all activity under your account.</li>
      <li>Don't share credentials or impersonate others.</li>
      <li>We may suspend or terminate accounts engaged in abuse, scraping, automated access, or attempts to compromise the service.</li>
    </ul>

    <h3>5. Acceptable Use</h3>
    <ul>
      <li>Don't reverse-engineer, decompile, or attempt to extract the source code of Kairo.</li>
      <li>Don't use Kairo to harass, deceive, or harm others, or to violate any law.</li>
      <li>Don't bypass rate limits, authentication, or security controls.</li>
    </ul>

    <h3>6. Intellectual Property</h3>
    <p>
      The Kairo name, branding, briefs, and synthesis are our property.
      You retain ownership of any content you submit; you grant us a limited
      license to display it back to you within the service.
    </p>

    <h3>7. Limitation of Liability</h3>
    <p>
      To the maximum extent permitted by law, Kairo and its operators are not
      liable for any direct, indirect, incidental, consequential, or punitive
      damages arising from your use of the service, including any trading or
      investment losses.
    </p>

    <h3>8. Changes</h3>
    <p>
      We may update these terms occasionally. Material changes will be
      announced in-product. Continued use after a change means you accept
      the updated terms.
    </p>

    <p class="modal-fineprint">
      Questions? Contact us at <strong>hello@kairo.app</strong>.
    </p>
  </div>
</div>

<!-- Privacy -->
<div id="privacy" class="auth-modal" role="dialog" aria-modal="true" aria-labelledby="privacy-title">
  <a class="auth-modal-backdrop" href="#close" aria-label="Close dialog"></a>
  <div class="auth-modal-card">
    <a class="auth-modal-close" href="#close" aria-label="Close">×</a>
    <h2 id="privacy-title">Privacy</h2>
    <p class="modal-sub">What we collect, why we collect it, and how we protect it.</p>

    <h3>What we store</h3>
    <ul>
      <li>Your username and (optional) email.</li>
      <li>Profile preferences you choose to share (name, profession, trading experience, purpose).</li>
      <li>A salted, PBKDF2-hashed copy of your password — never the password itself.</li>
      <li>Session tokens, stored only as HMAC hashes — the raw value never sits on our servers.</li>
    </ul>

    <h3>What we don't do</h3>
    <ul>
      <li>We don't sell or rent your personal data to advertisers or data brokers.</li>
      <li>We don't track you across other websites.</li>
      <li>We don't run third-party advertising or analytics that profile you.</li>
    </ul>

    <h3>Security</h3>
    <p>
      Sign-ins are rate-limited to defeat brute force. Failed attempts auto-lock
      an account for a short cool-down. Session tokens expire after periods of
      inactivity and are revoked when you change your password or sign out.
    </p>

    <h3>Your control</h3>
    <p>
      You can delete your account at any time from
      <strong>Profile → Danger Zone</strong>. Deletion removes your account,
      profile data, and all active sessions.
    </p>

    <p class="modal-fineprint">
      Privacy questions? Reach us at <strong>privacy@kairo.app</strong>.
    </p>
  </div>
</div>
"""


_PW_METER_CSS = """
<style>
.pw-meter {
  display: flex;
  gap: 4px;
  margin: 6px 0 4px;
}
.pw-meter span {
  flex: 1;
  height: 5px;
  border-radius: 99px;
  background: var(--hairline);
}
.pw-meter.lvl1 span:nth-child(-n+1) { background: oklch(0.65 0.15 30); }
.pw-meter.lvl2 span:nth-child(-n+2) { background: oklch(0.70 0.13 70); }
.pw-meter.lvl3 span:nth-child(-n+3) { background: oklch(0.65 0.12 130); }
.pw-meter.lvl4 span:nth-child(-n+4) { background: oklch(0.60 0.13 150); }
.pw-meter-label {
  font-size: 12px;
  color: var(--ink-3);
  font-weight: 600;
}
</style>
"""


def _render_login_page() -> None:
    """Show the Kairo login/register gate. Blocks the rest of the app via st.stop()."""
    from app.auth.user_manager import (
        AuthError, password_strength, validate_password, validate_username,
    )

    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    # ── Two-column layout via st.columns ────────────────────────────────
    hero_col, form_col = st.columns([0.7, 0.3])

    with hero_col:
        st.html(_AUTH_HERO_HTML)

    with form_col:
        st.html(
            """
            <h2>Welcome back</h2>
            <p class="auth-sub">Sign in to your Kairo workspace, or create an account in seconds.</p>
            """
        )

        sign_in_tab, register_tab = st.tabs(["Sign In", "Create Account"])

        # ── Sign in ──────────────────────────────────────────────────────
        with sign_in_tab:
            with st.form("login_form", clear_on_submit=False):
                username = st.text_input("Username", placeholder="your username", autocomplete="username")
                password = st.text_input("Password", type="password", placeholder="••••••••", autocomplete="current-password")
                remember_me = st.checkbox("Keep me signed in on this device", value=False,
                                          help="Issues a 30-day session token tied to this browser. Avoid on shared computers.")
                submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

            if submitted:
                mgr = _get_user_manager()
                if mgr is None:
                    st.error(
                        "Sign-in is temporarily unavailable. Please check back shortly. "
                        "(Administrator: configure MONGO_URI and restart the app.)"
                    )
                else:
                    generic_err = "Those credentials didn't match. Please try again."
                    try:
                        user = mgr.authenticate(username or "", password or "")
                    except AuthError as exc:
                        user = None
                        generic_err = str(exc) if exc.code == "locked" else generic_err
                    if user:
                        st.session_state["_kairo_user"] = user
                        st.session_state["_kairo_just_logged_in"] = True
                        if remember_me:
                            try:
                                _token = mgr.create_session_token(user["username"])
                                st.query_params["auto_session"] = _token
                                st.session_state["_kairo_session_token"] = _token
                            except Exception as _exc:
                                logger.warning("remember-me token creation failed: %s", _exc)
                        st.rerun()
                    else:
                        st.error(generic_err)

        # ── Create account ───────────────────────────────────────────────
        with register_tab:
            st.markdown(_PW_METER_CSS, unsafe_allow_html=True)

            new_user  = st.text_input("Username", placeholder="3–30 chars, lowercase letters & numbers", key="reg_user",
                                      autocomplete="username")
            new_email = st.text_input("Email (optional)", placeholder="you@example.com", key="reg_email",
                                      autocomplete="email")
            new_pass  = st.text_input("Password", type="password",
                                      placeholder="at least 10 chars, mix letters & numbers",
                                      key="reg_pass", autocomplete="new-password")

            if new_pass:
                score, label = password_strength(new_pass)
                st.html(
                    f'<div class="pw-meter lvl{score}"><span></span><span></span><span></span><span></span></div>'
                    f'<div class="pw-meter-label">Strength: {label}</div>',
                )

            with st.form("register_form", clear_on_submit=False):
                new_pass2 = st.text_input("Confirm password", type="password",
                                          placeholder="repeat password", key="reg_pass2",
                                          autocomplete="new-password")
                agreed = st.checkbox(
                    "I agree to use Kairo for educational/research purposes — Kairo briefs are not financial advice.",
                    key="reg_agree",
                )
                reg_submitted = st.form_submit_button("Create Account", use_container_width=True, type="primary")

            if reg_submitted:
                uname_err = validate_username(new_user)
                pw_err = validate_password(new_pass) if not uname_err else None
                if uname_err:
                    st.error(uname_err)
                elif pw_err:
                    st.error(pw_err)
                elif new_pass != new_pass2:
                    st.error("Passwords do not match.")
                elif not agreed:
                    st.error("Please accept the educational-use notice to continue.")
                else:
                    mgr = _get_user_manager()
                    if mgr is None:
                        st.error(
                            "Account creation is temporarily unavailable. Please check back shortly."
                        )
                    else:
                        try:
                            ok = mgr.create_user(new_user, new_pass, role="user", email=new_email or "")
                        except AuthError as exc:
                            ok = False
                            st.error(str(exc))
                        else:
                            if ok:
                                st.success("Account created. Sign in to continue.")
                            else:
                                st.error("We couldn't create that account. Try a different username.")

        st.html(
            '<p class="auth-meta">Kairo never shares your data. Sessions are encrypted, '
            'tokens are hashed at rest, and we rate-limit sign-in attempts.</p>',
        )

    st.html(_AUTH_FOOTER_AND_MODALS)

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
# Profile helpers
# ---------------------------------------------------------------------------

def _get_initials(profile: dict) -> str:
    first = (profile.get("first_name") or "").strip()
    last  = (profile.get("last_name")  or "").strip()
    if first and last:
        return (first[0] + last[0]).upper()
    if first:
        return first[:2].upper()
    return (profile.get("username") or "?")[:2].upper()


@st.fragment
def _profile_tab(user: dict, mgr) -> None:
    from app.auth.user_manager import PROFESSIONS, TRADING_PROFILES, PURPOSES

    username = user["username"]
    profile  = mgr.get_profile(username) or user

    filled = profile.get("profile_filled", 0)
    total  = profile.get("profile_total", 6)

    col, _ = st.columns([5, 2])
    with col:
        # ── Avatar + name ──────────────────────────────────────────────────
        initials = _get_initials(profile)
        display_name = " ".join(filter(None, [profile.get("first_name"), profile.get("last_name")])) or username
        st.markdown(
            f"""
            <div style="display:flex;align-items:center;gap:16px;margin-bottom:24px">
              <div style="
                width:58px;height:58px;border-radius:50%;
                background:var(--accent);color:var(--paper);
                display:grid;place-items:center;
                font-size:23px;font-weight:800;flex-shrink:0;letter-spacing:-0.02em;
              ">{initials}</div>
              <div>
                <div style="font-size:20px;font-weight:800;color:var(--ink);letter-spacing:-0.02em">
                  {display_name}
                </div>
                <div style="font-size:13px;color:var(--ink-3);margin-top:2px">
                  @{username}
                  <span style="
                    margin-left:8px;background:{'var(--accent)' if profile['role']=='admin' else 'var(--ink-3)'};
                    color:var(--paper);font-size:9px;font-weight:700;letter-spacing:0.08em;
                    text-transform:uppercase;padding:2px 7px;border-radius:99px;
                  ">{profile['role']}</span>
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Plus membership progress ───────────────────────────────────────
        if filled < total:
            st.info(
                f"✦ **Fill in all {total} profile details to get 1 month of free Plus membership!** "
                f"({filled} of {total} completed)"
            )
            st.progress(int(filled / total * 100))
        else:
            st.success("🎉 Profile complete — your free Plus month is active!")

        st.divider()

        # ── Edit profile form ──────────────────────────────────────────────
        st.subheader("Profile Details")
        st.caption("All fields are optional.")

        with st.form("profile_edit_form"):
            fc1, fc2 = st.columns(2)
            with fc1:
                new_first = st.text_input("First name", value=profile.get("first_name", ""), placeholder="Jane")
            with fc2:
                new_last = st.text_input("Last name",  value=profile.get("last_name",  ""), placeholder="Smith")

            new_email = st.text_input(
                "Email",
                value=profile.get("email", ""),
                placeholder="you@example.com",
            )

            _prof_opts = [""] + PROFESSIONS
            _prof_idx  = _prof_opts.index(profile.get("profession", "")) if profile.get("profession", "") in _prof_opts else 0
            new_profession = st.selectbox(
                "Profession",
                options=_prof_opts,
                index=_prof_idx,
                format_func=lambda x: x or "Select your profession…",
            )

            _trade_opts = [""] + TRADING_PROFILES
            _trade_idx  = _trade_opts.index(profile.get("trading_profile", "")) if profile.get("trading_profile", "") in _trade_opts else 0
            new_trading = st.selectbox(
                "Trading experience",
                options=_trade_opts,
                index=_trade_idx,
                format_func=lambda x: x or "Select your experience level…",
            )

            _purp_opts = [""] + PURPOSES
            _purp_idx  = _purp_opts.index(profile.get("purpose", "")) if profile.get("purpose", "") in _purp_opts else 0
            new_purpose = st.selectbox(
                "Why did you subscribe?",
                options=_purp_opts,
                index=_purp_idx,
                format_func=lambda x: x or "Select your purpose…",
            )

            save_btn = st.form_submit_button("Save Profile", use_container_width=True)

        if save_btn:
            mgr.update_profile(username, {
                "first_name":      new_first,
                "last_name":       new_last,
                "email":           new_email,
                "profession":      new_profession,
                "trading_profile": new_trading,
                "purpose":         new_purpose,
            })
            refreshed = mgr.get_profile(username)
            if refreshed:
                st.session_state["_kairo_user"] = refreshed
            st.success("Profile updated!")
            st.rerun()

        st.divider()

        # ── Change password ────────────────────────────────────────────────
        with st.expander("Change Password"):
            with st.form("change_password_form"):
                old_pw  = st.text_input("Current password",     type="password")
                new_pw1 = st.text_input("New password",         type="password",
                                         help="At least 10 characters, with letters and numbers.")
                new_pw2 = st.text_input("Confirm new password", type="password")
                pw_btn  = st.form_submit_button("Update Password", use_container_width=True)

            if pw_btn:
                from app.auth.user_manager import AuthError as _AE
                if not old_pw or not new_pw1:
                    st.error("Please fill in all password fields.")
                elif new_pw1 != new_pw2:
                    st.error("Passwords do not match.")
                else:
                    try:
                        ok = mgr.change_password(username, old_pw, new_pw1)
                    except _AE as _ae:
                        st.error(str(_ae))
                    else:
                        if ok:
                            st.success(
                                "Password changed. Other sessions have been signed out — "
                                "sign in again on any other devices."
                            )
                            # Re-issue a session token for this tab so the user
                            # isn't accidentally bumped out of the page they're on.
                            try:
                                _new_tok = mgr.create_session_token(username)
                                st.session_state["_kairo_session_token"] = _new_tok
                                st.query_params["auto_session"] = _new_tok
                            except Exception:
                                pass
                        else:
                            st.error("Current password is incorrect.")

        st.divider()

        # ── Sign out ───────────────────────────────────────────────────────
        if st.button("Sign out", key="profile_tab_signout", use_container_width=True, type="secondary"):
            _tok = st.session_state.pop("_kairo_session_token", None)
            if _tok:
                try:
                    mgr.invalidate_session_token(_tok)
                except Exception:
                    logger.warning("Server-side session invalidation failed during sign-out.")
            for _k in [k for k in list(st.session_state.keys()) if k.startswith("_kairo")]:
                st.session_state.pop(_k, None)
            st.query_params.clear()
            st.rerun()

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
    import os as _os

    _mongo_uri = _os.getenv("MONGO_URI") or _Cfg.MONGO_URI
    _mongo_db  = _os.getenv("MONGO_DB")  or _Cfg.MONGO_DB or "kairo"
    _user_id   = "default"

    _BACKFILL_PRESETS = {
        "2 days": 2, "1 week": 7, "1 month": 30,
        "3 months": 90, "6 months": 180, "1 year": 365,
    }

    # ── Table ─────────────────────────────────────────────────────────────────
    _h1, _h2, _h3, _h4 = st.columns([2, 2, 2, 2])
    with _h1: st.markdown("**Data Source**")
    with _h2: st.markdown("**Ingestion (last 24h)**")
    with _h3: st.markdown("**Purge All**")
    with _h4: st.markdown("**Backfill**")

    st.markdown(
        "<hr style='margin:6px 0 14px;border-color:var(--hairline)'>",
        unsafe_allow_html=True,
    )

    # Row 1: Narratives
    _r1c1, _r1c2, _r1c3, _r1c4 = st.columns([2, 2, 2, 2])
    with _r1c1: st.markdown("**Narratives**")
    with _r1c2: _narr_ingest   = st.button("Run",      key="btn_narr_ingest",   use_container_width=True)
    with _r1c3: _narr_purge    = st.button("Purge",    key="btn_narr_purge",    use_container_width=True, type="secondary")
    with _r1c4: _narr_backfill = st.button("Backfill", key="btn_narr_backfill", use_container_width=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # Row 2: Market Analysis
    _r2c1, _r2c2, _r2c3, _r2c4 = st.columns([2, 2, 2, 2])
    with _r2c1: st.markdown("**Market Analysis**")
    with _r2c2: _mkt_ingest    = st.button("Run",   key="btn_mkt_ingest", use_container_width=True)
    with _r2c3: _mkt_purge     = st.button("Purge", key="btn_mkt_purge",  use_container_width=True, type="secondary")
    with _r2c4: st.markdown("—")

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # Row 3: Policy Updates
    _r3c1, _r3c2, _r3c3, _r3c4 = st.columns([2, 2, 2, 2])
    with _r3c1: st.markdown("**Policy Updates**")
    with _r3c2: _pol_ingest    = st.button("Run",      key="btn_pol_ingest",    use_container_width=True)
    with _r3c3: _pol_purge     = st.button("Purge",    key="btn_pol_purge",     use_container_width=True, type="secondary")
    with _r3c4: _pol_backfill  = st.button("Backfill", key="btn_pol_backfill",  use_container_width=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # Row 4: Concept Extractor / Education
    _r4c1, _r4c2, _r4c3, _r4c4 = st.columns([2, 2, 2, 2])
    with _r4c1: st.markdown("**Concept Extractor**")
    with _r4c2: _con_ingest    = st.button("Run",   key="btn_con_ingest", use_container_width=True)
    with _r4c3: _con_purge     = st.button("Purge", key="btn_con_purge",  use_container_width=True, type="secondary")
    with _r4c4: st.markdown("—")

    st.divider()

    # ── Action dispatch ───────────────────────────────────────────────────────
    # Priority order: purge confirmations → options panels → set-pending → run

    # ── Purge confirmations ───────────────────────────────────────────────────
    if st.session_state.get("_narr_purge_pending"):
        st.warning("Permanently delete **all narratives**? This cannot be undone.")
        _pc1, _pc2 = st.columns(2)
        with _pc1:
            if st.button("Confirm", key="_narr_purge_yes", type="primary", use_container_width=True):
                if _tracker:
                    _n = _tracker.purge_narratives(_user_id)
                    st.session_state.pop("_narr_purge_pending", None)
                    _cached_build_data.clear()
                    st.success(f"Deleted {_n} narrative(s).")
                    st.rerun()
                else:
                    st.error("MongoDB tracker not connected.")
        with _pc2:
            if st.button("Cancel", key="_narr_purge_no", use_container_width=True):
                st.session_state.pop("_narr_purge_pending", None)
                st.rerun()

    elif st.session_state.get("_mkt_purge_pending"):
        st.warning("Permanently delete **all market analysis data**? This cannot be undone.")
        _pc1, _pc2 = st.columns(2)
        with _pc1:
            if st.button("Confirm", key="_mkt_purge_yes", type="primary", use_container_width=True):
                try:
                    from pymongo import MongoClient as _MC
                    from config.config import mongo_tls_ca_file as _tls
                    from pymongo.server_api import ServerApi as _SA
                    _c = _MC(_mongo_uri, tlsCAFile=_tls(), server_api=_SA("1"), connect=False)
                    _c[_mongo_db]["crypto_markets_config"].drop()
                    _c.close()
                    st.session_state.pop("_mkt_purge_pending", None)
                    _cached_build_data.clear()
                    st.success("Market data purged.")
                    st.rerun()
                except Exception as _exc:
                    st.error(f"Purge failed: {_exc}")
        with _pc2:
            if st.button("Cancel", key="_mkt_purge_no", use_container_width=True):
                st.session_state.pop("_mkt_purge_pending", None)
                st.rerun()

    elif st.session_state.get("_pol_purge_pending"):
        st.warning("Permanently delete **all policy/regulation data**? This cannot be undone.")
        _pc1, _pc2 = st.columns(2)
        with _pc1:
            if st.button("Confirm", key="_pol_purge_yes", type="primary", use_container_width=True):
                try:
                    from pymongo import MongoClient as _MC
                    from config.config import mongo_tls_ca_file as _tls
                    from pymongo.server_api import ServerApi as _SA
                    _c = _MC(_mongo_uri, tlsCAFile=_tls(), server_api=_SA("1"), connect=False)
                    _c[_mongo_db]["crypto_regulations"].drop()
                    _c[_mongo_db]["regulation_runs"].drop()
                    _c.close()
                    st.session_state.pop("_pol_purge_pending", None)
                    _cached_build_data.clear()
                    st.success("Policy data purged.")
                    st.rerun()
                except Exception as _exc:
                    st.error(f"Purge failed: {_exc}")
        with _pc2:
            if st.button("Cancel", key="_pol_purge_no", use_container_width=True):
                st.session_state.pop("_pol_purge_pending", None)
                st.rerun()

    elif st.session_state.get("_con_purge_pending"):
        st.warning("Permanently delete **all concept extractor data**? This cannot be undone.")
        _pc1, _pc2 = st.columns(2)
        with _pc1:
            if st.button("Confirm", key="_con_purge_yes", type="primary", use_container_width=True):
                _con_trk2 = _get_concept_tracker()
                if _con_trk2:
                    _n = _con_trk2.purge_all()
                    st.session_state.pop("_con_purge_pending", None)
                    _cached_build_data.clear()
                    st.success(f"Deleted {_n} concept(s).")
                    st.rerun()
                else:
                    st.error("ConceptTracker not connected.")
        with _pc2:
            if st.button("Cancel", key="_con_purge_no", use_container_width=True):
                st.session_state.pop("_con_purge_pending", None)
                st.rerun()

    # ── Narratives backfill options ───────────────────────────────────────────
    elif st.session_state.get("_backfill_pending") == "narratives":
        st.markdown("**Narratives — Backfill options**")
        _bf_period = st.selectbox(
            "Backfill period",
            options=list(_BACKFILL_PRESETS.keys()),
            index=4,
            key="_narr_bf_period",
        )
        _bf_days   = _BACKFILL_PRESETS[_bf_period]
        _n_chunks  = (_bf_days + 6) // 7
        _fetch_onchain = st.checkbox(
            "Also fetch on-chain data for this period before synthesizing",
            value=False,
            key="_narr_bf_fetch",
            help=(
                "Unchecked (default): synthesize from existing Elasticsearch data — fast. "
                "Checked: fetch fresh on-chain data first (adds significant time)."
            ),
        )
        st.caption(
            f"{_bf_period} → {_n_chunks} weekly Gemini call(s)"
            + (" + on-chain data fetch" if _fetch_onchain else " · synthesize only")
        )
        _bfc1, _bfc2 = st.columns(2)
        with _bfc1:
            _narr_bf_run = st.button("Run Backfill", key="_narr_bf_run", type="primary", use_container_width=True)
        with _bfc2:
            if st.button("Cancel", key="_narr_bf_cancel", use_container_width=True):
                st.session_state.pop("_backfill_pending", None)
                st.rerun()

        if _narr_bf_run:
            st.session_state.pop("_backfill_pending", None)
            if _fetch_onchain:
                from datetime import timedelta as _td
                try:
                    _pipeline = _build_pipeline()
                except Exception as exc:
                    st.error(f"Pipeline init failed: {exc}")
                    logger.exception("Pipeline init failed")
                    return
                _now     = datetime.now(timezone.utc)
                _prog_oc = st.progress(0, text=f"On-chain chunk 1/{_n_chunks}…")
                for _i in range(_n_chunks):
                    _chunk_end = _now - _td(weeks=_i)
                    _prog_oc.progress(
                        int(50 * _i / _n_chunks),
                        text=f"On-chain chunk {_i + 1}/{_n_chunks}: week ending {_chunk_end.date()}",
                    )
                    try:
                        _pipeline.run_all(
                            end_time=_chunk_end.strftime("%Y-%m-%d %H:%M:%S"),
                            time_window_hours=168,
                        )
                    except Exception as exc:
                        st.warning(f"Chunk {_i + 1} failed: {exc}")
                        logger.exception("On-chain backfill chunk %d failed", _i + 1)
                _prog_oc.progress(50, text="On-chain fetch done. Starting Gemini synthesis…")
            _run_narrative_backfill_flow(
                _es, _engine, _tracker, _user_id,
                backfill_days=_bf_days,
                sleep_between=15,
            )

    # ── Policy Updates backfill options ──────────────────────────────────────
    elif st.session_state.get("_backfill_pending") == "policy":
        st.markdown("**Policy Updates — Backfill options**")
        _bf_period = st.selectbox(
            "Backfill period",
            options=list(_BACKFILL_PRESETS.keys()),
            index=4,
            key="_pol_bf_period",
        )
        _fetch_web = st.checkbox(
            "Also fetch fresh regulation data from web before synthesizing",
            value=False,
            key="_pol_bf_fetch",
            help=(
                "Unchecked (default): uses regulations already in MongoDB. "
                "Checked: calls Gemini to pull new regulatory developments from web trackers."
            ),
        )
        st.caption(
            "Synthesize only — using existing MongoDB regulations." if not _fetch_web
            else f"Fetch {_bf_period} of regulation data from web trackers via Gemini → deduplicate → store."
        )
        _bfc1, _bfc2 = st.columns(2)
        with _bfc1:
            _pol_bf_run = st.button("Run Backfill", key="_pol_bf_run", type="primary", use_container_width=True)
        with _bfc2:
            if st.button("Cancel", key="_pol_bf_cancel", use_container_width=True):
                st.session_state.pop("_backfill_pending", None)
                st.rerun()

        if _pol_bf_run:
            st.session_state.pop("_backfill_pending", None)
            _reg_tracker = _get_regulation_tracker()
            if not _reg_tracker:
                st.warning("MongoDB not configured — RegulationTracker unavailable.")
            elif _engine is None:
                st.error("Gemini not configured. Check GEMINI_KEY.")
            elif not _fetch_web:
                try:
                    _existing = _reg_tracker.get_latest_regulations(limit=1000)
                    st.info(
                        f"Found **{len(_existing)}** regulation(s) already in MongoDB. "
                        "Enable the checkbox to pull fresh web data."
                    )
                except Exception as _exc:
                    st.error(f"Failed to read regulations: {_exc}")
            else:
                _reg_prog = st.progress(0, text=f"Querying Gemini for {_bf_period} of regulatory history…")
                _reg_stat = st.empty()
                try:
                    _reg_prog.progress(40, text="Sending prompt to Gemini…")
                    _result  = _reg_tracker.fetch_and_store(_engine)
                    _reg_prog.progress(100, text="Done.")
                    if "error" in _result:
                        _reg_stat.error(f"Backfill failed: {_result['error']}")
                    else:
                        _saved   = _result.get("saved", 0)
                        _skipped = _result.get("skipped", 0)
                        _reg_stat.success(
                            f"Backfill complete — {_saved} regulation(s) added, {_skipped} already known."
                        )
                    _cached_build_data.clear()
                    st.rerun()
                except Exception as _exc:
                    _reg_prog.empty()
                    st.error(f"Backfill failed: {_exc}")
                    logger.exception("Policy backfill failed")

    # ── Market Analysis ingestion options ─────────────────────────────────────
    elif st.session_state.get("_mkt_options_pending"):
        st.markdown("**Market Analysis — Ingestion options**")
        _discover_roadmaps = st.checkbox(
            "Discover roadmaps (fetches roadmap pages per project)",
            value=False,
            key="_mkt_roadmap",
            help=(
                "Unchecked (default): faster, uses Gemini knowledge only. "
                "Checked: fetches each project's roadmap page — adds 15–30 min."
            ),
        )
        st.caption(
            "Fast mode — Gemini knowledge only." if not _discover_roadmaps
            else "Roadmap pages will be fetched for each of the top 20 projects."
        )
        _mc1, _mc2 = st.columns(2)
        with _mc1:
            _mkt_run = st.button("Run Ingestion", key="_mkt_run_opt", type="primary", use_container_width=True)
        with _mc2:
            if st.button("Cancel", key="_mkt_cancel_opt", use_container_width=True):
                st.session_state.pop("_mkt_options_pending", None)
                st.rerun()

        if _mkt_run:
            st.session_state.pop("_mkt_options_pending", None)
            _cmc_key = _Cfg.CMC_API_KEY
            if not _cmc_key:
                st.error("CMC_API_KEY not configured. Set it in your environment or Streamlit secrets.")
            else:
                _mkt_prog = st.progress(0, text="Fetching CoinMarketCap data…")
                _mkt_stat = st.empty()
                try:
                    from app.ingestion.crypto_markets import CryptoMarketsUpdater
                    _mkt_prog.progress(15, text="Calling CoinMarketCap API…")
                    _upd      = CryptoMarketsUpdater(_cmc_key, _mongo_uri, _mongo_db)
                    _projects = _upd.build_projects(discover_roadmaps=_discover_roadmaps)
                    _mkt_prog.progress(55, text="Saving to MongoDB…")
                    _upd.save_to_mongo(_projects)
                    _mkt_prog.progress(65, text="Running AI analysis…")
                    from app.markets.analyzer import MarketAnalyzer
                    _analyzer = MarketAnalyzer(_mongo_uri, _mongo_db)
                    def _mkt_cb(current, total, name):
                        pct = 65 + int(30 * current / total)
                        _mkt_prog.progress(pct, text=f"Analysed {name} ({current}/{total})…")
                    _results  = _analyzer.analyze_all(
                        fetch_pages=_discover_roadmaps, dry_run=False, progress_cb=_mkt_cb
                    )
                    _ok = sum(1 for r in _results if not r.get("analysis_error"))
                    _cached_build_data.clear()
                    _mkt_prog.progress(100, text="Done.")
                    _mkt_stat.success(
                        f"Updated {len(_projects)} projects, {_ok} analysed. Switch to Markets tab."
                    )
                    st.rerun()
                except Exception as _exc:
                    _mkt_prog.empty()
                    st.error(f"Markets update failed: {_exc}")
                    logger.exception("Markets update failed")

    # ── Concept Extractor ingestion options ───────────────────────────────────
    elif st.session_state.get("_con_options_pending"):
        st.markdown("**Concept Extractor / Education — options**")
        _con_url = st.text_input(
            "Source URL (optional)",
            placeholder="https://www.scs.org.sg/articles/cryptocurrency-singapore",
            key="_con_url_input",
            help=(
                "Leave blank: prompt is sent as-is, Gemini uses its knowledge + default sources in the prompt. "
                "Enter a URL: the URL is appended to the prompt so Gemini fetches and reads that page."
            ),
        )
        _con_url_stripped = _con_url.strip()
        st.caption(
            "No URL — Gemini uses its knowledge + default sources." if not _con_url_stripped
            else f"URL will be passed to Gemini: {_con_url_stripped}"
        )
        _cc1, _cc2 = st.columns(2)
        with _cc1:
            _con_run = st.button("Run", key="_con_run_opt", type="primary", use_container_width=True)
        with _cc2:
            if st.button("Cancel", key="_con_cancel_opt", use_container_width=True):
                st.session_state.pop("_con_options_pending", None)
                st.rerun()

        if _con_run:
            st.session_state.pop("_con_options_pending", None)
            _con_trk_adm = _get_concept_tracker()
            if not _con_trk_adm:
                st.warning("MongoDB not configured — ConceptTracker unavailable.")
            elif _engine is None:
                st.error("Gemini not configured. Check GEMINI_KEY.")
            else:
                _con_prog = st.progress(0, text="Preparing concept extraction…")
                _con_stat = st.empty()
                try:
                    if _con_url_stripped:
                        _con_prog.progress(20, text="Fetching page content…")
                    _con_prog.progress(40, text="Sending prompt to Gemini…")
                    _result = _con_trk_adm.fetch_and_store_from_url(_engine, _con_url_stripped)
                    _con_prog.progress(100, text="Done.")
                    if "error" in _result:
                        _con_stat.error(f"Extraction failed: {_result['error']}")
                    else:
                        _sv  = _result.get("saved", 0)
                        _sk  = _result.get("skipped", 0)
                        _tot = _result.get("total_found", 0)
                        _grp = _result.get("groups_updated", 0)
                        if _sv:
                            _con_stat.success(
                                f"{_sv} concept(s) added, {_sk} already known "
                                f"(of {_tot} found) · {_grp} group(s) updated."
                            )
                        else:
                            _con_stat.info(
                                f"No new concepts — {_sk} already known (of {_tot} found)."
                            )
                    _cached_build_data.clear()
                except Exception as _exc:
                    _con_prog.empty()
                    st.error(f"Concept extraction failed: {_exc}")
                    logger.exception("Concept extraction failed")

    # ── Set pending state on fresh button clicks ──────────────────────────────
    elif _narr_purge:
        st.session_state["_narr_purge_pending"] = True
        st.rerun()
    elif _mkt_purge:
        st.session_state["_mkt_purge_pending"] = True
        st.rerun()
    elif _pol_purge:
        st.session_state["_pol_purge_pending"] = True
        st.rerun()
    elif _con_purge:
        st.session_state["_con_purge_pending"] = True
        st.rerun()
    elif _narr_backfill:
        st.session_state["_backfill_pending"] = "narratives"
        st.rerun()
    elif _pol_backfill:
        st.session_state["_backfill_pending"] = "policy"
        st.rerun()
    elif _mkt_ingest:
        st.session_state["_mkt_options_pending"] = True
        st.rerun()
    elif _con_ingest:
        st.session_state["_con_options_pending"] = True
        st.rerun()

    # ── Immediate run actions (no pre-options needed) ─────────────────────────
    elif _narr_ingest:
        st.markdown("**Narratives — Ingestion (24h)**")
        try:
            _pipeline = _build_pipeline()
        except Exception as exc:
            st.error(f"Pipeline init failed: {exc}")
            logger.exception("Pipeline init failed")
            return
        _now     = datetime.now(timezone.utc)
        _end_str = _now.strftime("%Y-%m-%d %H:%M:%S")
        _prog    = st.progress(0, text=f"Running {_Cfg.INGESTION_PROVIDER} pipeline (24h)…")
        _stat    = st.empty()
        try:
            _prog.progress(20, text="Fetching on-chain data…")
            _res           = _pipeline.run_all(end_time=_end_str, time_window_hours=24)
            _total_rows    = sum(r.rows_fetched for r in _res.values())
            _total_indexed = sum(r.docs_indexed for r in _res.values())
            _errors        = [f"[{r.query_name}] {r.error}" for r in _res.values() if r.error]
            _prog.progress(50, text="Running narrative detection…")
        except Exception as exc:
            _prog.empty()
            st.error(f"Ingestion failed: {exc}")
            logger.exception("Ingestion failed")
            return
        _cached_build_data.clear()
        if _errors:
            _stat.warning(f"Ingested {_total_rows:,} rows ({_total_indexed:,} indexed) — {len(_errors)} error(s)")
        else:
            _stat.info(f"Ingested {_total_rows:,} rows, {_total_indexed:,} indexed.")
        _run_detection_flow(_es, _engine, _tracker, _user_id, hours=24)

    elif _pol_ingest:
        st.markdown("**Policy Updates — Ingestion (24h)**")
        _reg_tracker = _get_regulation_tracker()
        if not _reg_tracker:
            st.warning("MongoDB not configured — RegulationTracker unavailable. Set MONGO_URI.")
        elif _engine is None:
            st.error("Gemini not configured. Check GEMINI_KEY.")
        else:
            _reg_prog = st.progress(0, text="Calling Gemini for regulatory intelligence…")
            _reg_stat = st.empty()
            try:
                _reg_prog.progress(40, text="Sending prompt to Gemini…")
                _result  = _reg_tracker.fetch_and_store(_engine)
                _reg_prog.progress(100, text="Done.")
                if "error" in _result:
                    _reg_stat.error(f"Regulation fetch failed: {_result['error']}")
                else:
                    _saved   = _result.get("saved", 0)
                    _skipped = _result.get("skipped", 0)
                    _total   = _result.get("total_found", 0)
                    if _saved:
                        _reg_stat.success(
                            f"{_saved} new regulation(s) saved, {_skipped} skipped (of {_total} found)."
                        )
                    else:
                        _reg_stat.info(
                            f"No new regulations — {_skipped} already known (of {_total} found)."
                        )
                _cached_build_data.clear()
                st.rerun()
            except Exception as _exc:
                _reg_prog.empty()
                st.error(f"Regulation fetch failed: {_exc}")
                logger.exception("Regulation fetch failed")


def run() -> None:
    """Entry point called by streamlit_app.py on every Streamlit rerun."""
    st.set_page_config(
        page_title="Kairo",
        page_icon="🔮",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Inject CSS immediately — before any query-param logic or st.rerun() calls —
    # so the browser receives chrome-hiding styles as the very first DOM update.
    # This prevents Streamlit's status widget / "Running…" overlay from flashing
    # on cold load AND between reruns (e.g. after login form submission).
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
          --r-sm: 10px; --r-md: 16px; --r-lg: 22px; --r-xl: 28px;
          --shadow-card: 0 1px 2px oklch(0.5 0.02 60 / 0.05), 0 6px 22px oklch(0.5 0.02 60 / 0.06);
        }

        /* ── Chrome / chrome resets ── */
        #MainMenu, header, footer { display: none !important; }
        .stApp { padding: 0 !important; background: var(--paper) !important; }
        .block-container { padding: 0 !important; max-width: 100% !important; }
        div[data-testid="stVerticalBlock"] { gap: 0 !important; }
        iframe { border: none !important; }

        /* ── Hide ALL Streamlit running/status indicators ── */
        [data-testid="stStatusWidget"] { display: none !important; }
        [data-testid="stHeader"] { display: none !important; }
        [data-testid="toastContainer"] { display: none !important; }
        .stToast { display: none !important; }

        /* ── Suppress the "stale content" grey overlay during reruns ──
           Streamlit dims existing elements with opacity while the new render
           comes in. Locking opacity to 1 and removing transitions makes
           the login→home switch (and any rerun) appear instant. */
        [data-stale], [data-stale="true"] { opacity: 1 !important; transition: none !important; }
        .stApp, .stApp > div, .main, .block-container {
          opacity: 1 !important;
          transition: none !important;
        }
        /* Warm page background so there is never a white/grey flash */
        html, body { background: var(--paper) !important; }

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

        /* ── Running indicator — hide it, show loading inside the iframe ── */
        [data-testid="stStatusWidget"] { display: none !important; }

        /* ── Branded data-loading state ───────────────────────────────────── */
        [data-testid="stSpinner"] {
          display: flex !important;
          flex-direction: column !important;
          align-items: center !important;
          justify-content: center !important;
          padding: 80px 24px !important;
          background: var(--paper) !important;
          min-height: 320px !important;
        }
        [data-testid="stSpinner"] > div {
          display: flex !important;
          flex-direction: column !important;
          align-items: center !important;
          gap: 18px !important;
        }
        [data-testid="stSpinner"] i,
        [data-testid="stSpinner"] svg {
          width: 36px !important;
          height: 36px !important;
          color: var(--accent) !important;
          stroke: var(--accent) !important;
          fill: var(--accent) !important;
          opacity: 0.85;
        }
        [data-testid="stSpinner"] > div > div:last-child,
        [data-testid="stSpinner"] p {
          font-size: 15.5px !important;
          font-weight: 600 !important;
          color: var(--ink-2) !important;
          letter-spacing: -0.01em !important;
          text-align: center !important;
          max-width: 420px !important;
          line-height: 1.5 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Handle actions triggered by the React iframe via query params
    def _preserve_session_token():
        """Clear action params but keep auto_session so remember-me persists in URL."""
        _tok = st.query_params.get("auto_session", "")
        st.query_params.clear()
        if _tok:
            st.query_params["auto_session"] = _tok

    _qp = st.query_params.get("kairo_action", "")
    if _qp == "logout":
        _tok = (
            st.session_state.pop("_kairo_session_token", None)
            or st.query_params.get("auto_session", "")
        )
        if _tok:
            try:
                _mgr_l = _get_user_manager()
                if _mgr_l:
                    _mgr_l.invalidate_session_token(_tok)
            except Exception:
                logger.warning("Server-side session invalidation failed during logout.")

        # Wipe everything namespaced to Kairo from session_state so no previous
        # user's data leaks into the next sign-in on the same Streamlit session.
        for _k in [k for k in list(st.session_state.keys()) if k.startswith("_kairo")]:
            st.session_state.pop(_k, None)
        st.session_state.pop("admin_user_id", None)

        # Purge any per-user cached data so the iframe can't render stale content.
        try:
            _cached_build_data.clear()
        except Exception:
            pass

        st.query_params.clear()

        # Scrub the URL on the client side too — Streamlit only clears the
        # query string for the next rerun, but a leftover `auto_session` token
        # would still sit in the browser's address bar / history.
        st.components.v1.html(
            """
            <script>
              try {
                const u = new URL(window.top.location.href);
                u.searchParams.delete('auto_session');
                u.searchParams.delete('kairo_action');
                window.top.history.replaceState({}, '', u.toString());
              } catch (e) {}
              try { window.top.sessionStorage && window.top.sessionStorage.clear(); } catch (e) {}
            </script>
            """,
            height=0,
        )
        st.rerun()
    elif _qp == "save-profile":
        _raw = st.query_params.get("profile_data", "")
        if _raw and st.session_state.get("_kairo_user"):
            try:
                import json as _json
                _updates = _json.loads(_raw)
                _mgr2 = _get_user_manager()
                if _mgr2:
                    _uname = st.session_state["_kairo_user"]["username"]
                    _mgr2.update_profile(_uname, _updates)
                    _refreshed = _mgr2.get_profile(_uname)
                    if _refreshed:
                        st.session_state["_kairo_user"] = _refreshed
            except Exception as _exc:
                logger.warning("save-profile failed: %s", _exc)
        st.session_state["_kairo_init_view"] = "profile"
        st.session_state["_kairo_toast"] = "Profile saved!"
        _preserve_session_token()
        st.rerun()
    elif _qp == "change-password":
        _pw_raw = st.query_params.get("pw_data", "")
        if _pw_raw and st.session_state.get("_kairo_user"):
            from app.auth.user_manager import AuthError as _AuthErr
            try:
                import json as _json
                _pw_data = _json.loads(_pw_raw)
                _mgr_pw = _get_user_manager()
                if _mgr_pw:
                    _uname = st.session_state["_kairo_user"]["username"]
                    try:
                        _ok = _mgr_pw.change_password(
                            _uname, _pw_data.get("old", ""), _pw_data.get("new", "")
                        )
                    except _AuthErr as _ae:
                        _ok = False
                        st.session_state["_kairo_pw_result"] = "weak_password"
                        st.session_state["_kairo_pw_message"] = str(_ae)
                    else:
                        if _ok:
                            # Password rotation revokes every existing session
                            # for this user (see UserManager). Re-issue a fresh
                            # session token for the current device so the user
                            # isn't surprise-logged-out of the tab they're in.
                            st.session_state["_kairo_pw_result"] = "ok"
                            try:
                                _new_tok = _mgr_pw.create_session_token(_uname)
                                st.session_state["_kairo_session_token"] = _new_tok
                                st.query_params["auto_session"] = _new_tok
                            except Exception:
                                pass
                        elif "_kairo_pw_result" not in st.session_state:
                            st.session_state["_kairo_pw_result"] = "wrong_password"
            except Exception as _exc:
                logger.warning("change-password failed: %s", _exc)
                st.session_state["_kairo_pw_result"] = "error"
        st.session_state["_kairo_init_view"] = "profile"
        _preserve_session_token()
        st.rerun()
    elif _qp == "delete-account":
        _confirm = st.query_params.get("confirm_user", "")
        if st.session_state.get("_kairo_user"):
            _uname = st.session_state["_kairo_user"]["username"]
            if _confirm == _uname:
                _mgr_del = _get_user_manager()
                if _mgr_del:
                    # delete_user also drops every session for this username.
                    _mgr_del.delete_user(_uname)
                # Reuse the logout cleanup: wipe everything kairo-namespaced
                # plus admin user id, plus any cached per-user data.
                for _k in [k for k in list(st.session_state.keys()) if k.startswith("_kairo")]:
                    st.session_state.pop(_k, None)
                st.session_state.pop("admin_user_id", None)
                try:
                    _cached_build_data.clear()
                except Exception:
                    pass
                st.components.v1.html(
                    """
                    <script>
                      try {
                        const u = new URL(window.top.location.href);
                        u.searchParams.delete('auto_session');
                        u.searchParams.delete('kairo_action');
                        window.top.history.replaceState({}, '', u.toString());
                      } catch (e) {}
                    </script>
                    """,
                    height=0,
                )
        st.query_params.clear()
        st.rerun()


    # ── Auth gate ─────────────────────────────────────────────────────────────
    current_user = st.session_state.get("_kairo_user")
    if not current_user:
        # Try remember-me token from URL — only load user manager if token is present
        _rm_token = st.query_params.get("auto_session", "")
        if _rm_token:
            mgr = _get_user_manager()
            if mgr:
                try:
                    _rm_uname = mgr.validate_session_token(_rm_token)
                    if _rm_uname:
                        _rm_profile = mgr.get_profile(_rm_uname)
                        if _rm_profile:
                            st.session_state["_kairo_user"] = _rm_profile
                            st.session_state["_kairo_session_token"] = _rm_token
                            current_user = _rm_profile
                except Exception as _exc:
                    logger.warning("remember-me validation failed: %s", _exc)
    if not current_user:
        _render_login_page()  # calls st.stop() — nothing below runs
    is_admin = current_user.get("role") == "admin"

    # ── Post-login loading screen: pre-warm slow caches so the app renders instantly ──
    if st.session_state.pop("_kairo_just_logged_in", False):
        _first_name = (current_user.get("first_name") or current_user.get("username") or "").strip()
        st.markdown(
            f"""
            <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
                        height:80vh;font-family:ui-sans-serif,system-ui,sans-serif;gap:0">
              <div style="font-size:32px;font-weight:800;color:#c46a43;letter-spacing:-0.03em;margin-bottom:12px">Kairo</div>
              <div style="font-size:16px;color:#888;">{"Welcome back, " + _first_name + "!" if _first_name else "Welcome!"} Setting up your workspace…</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        try: _get_concept_tracker()
        except Exception: pass
        try: _get_regulation_tracker()
        except Exception: pass
        try: init_services()
        except Exception: pass
        st.rerun()

    # ── Tab layout ───────────────────────────────────────────────────────────
    if is_admin:
        _tabs = st.tabs(["Kairo", "⚙ Admin"])
        tab_kairo, tab_admin = _tabs[0], _tabs[1]
        with tab_admin:
            _admin_panel()
    else:
        _tabs = st.tabs(["Kairo"])
        tab_kairo = _tabs[0]

    # ── Kairo tab — iframe only ───────────────────────────────────────────────
    with tab_kairo:
        user_id        = st.session_state.get("admin_user_id", "default")
        hours_lookback = int(st.session_state.get("detect_hours_input", _Cfg.DUNE_QUERY_WINDOW_HOURS))

        kairo_data = _cached_build_data(user_id, hours_lookback)
        kairo_data.setdefault("config", {})["dune_query_window_hours"] = _Cfg.DUNE_QUERY_WINDOW_HOURS
        # Inject auth profile under a separate key — kairo_data["user"] is the
        # morning-brief user section ({name, date, summary}); don't overwrite it.
        kairo_data["auth_user"] = dict(current_user)
        # Inject latest regulations for the Policy Pulse tab
        try:
            _reg_trk = _get_regulation_tracker()
            if _reg_trk:
                kairo_data["regulations"] = _reg_trk.get_latest_regulations(limit=60)
                kairo_data["regulation_last_run"] = _reg_trk.get_last_run() or {}
            else:
                kairo_data.setdefault("regulations", [])
                kairo_data.setdefault("regulation_last_run", {})
        except Exception as _exc:
            logger.warning("Failed to load regulations for kairo_data: %s", _exc)
            kairo_data.setdefault("regulations", [])
            kairo_data.setdefault("regulation_last_run", {})
        # Inject Crypto 101 concepts + groupings
        try:
            _con_trk = _get_concept_tracker()
            if _con_trk:
                kairo_data["concepts"]       = _con_trk.get_all_concepts()
                kairo_data["concept_groups"] = _con_trk.get_all_groups()
            else:
                kairo_data.setdefault("concepts", [])
                kairo_data.setdefault("concept_groups", [])
        except Exception as _exc:
            logger.warning("Failed to load concepts for kairo_data: %s", _exc)
            kairo_data.setdefault("concepts", [])
            kairo_data.setdefault("concept_groups", [])

        # Inject one-time transient UI signals (popped so they don't repeat on refresh)
        _init_view = st.session_state.pop("_kairo_init_view", None)
        _toast = st.session_state.pop("_kairo_toast", None)
        _pw_result = st.session_state.pop("_kairo_pw_result", None)
        _pw_message = st.session_state.pop("_kairo_pw_message", None)
        if _init_view:
            kairo_data["config"]["initial_view"] = _init_view
        if _toast:
            kairo_data["config"]["toast"] = _toast
        if _pw_result:
            kairo_data["config"]["pw_result"] = _pw_result
        if _pw_message:
            kairo_data["config"]["pw_message"] = _pw_message

        try:
            data_json_str = json.dumps(kairo_data, cls=_KairoEncoder, ensure_ascii=False)
        except Exception as exc:
            logger.exception("JSON serialisation failed: %s", exc)
            from app.synthesize.kairo_data import _empty_data
            data_json_str = json.dumps(_empty_data(), ensure_ascii=False)

        html = build_kairo_html(data_json_str)
        st.components.v1.html(html, height=900, scrolling=False)
