import streamlit as st
import streamlit.components.v1 as components
import json
import os
import logging
from datetime import datetime, timezone

from pathlib import Path
from brain.elasticsearch_manager import ElasticsearchManager
from synthesize.narrative_engine import NarrativeEngine
from synthesize.narrative_tracker import NarrativeTracker
from synthesize.kairo_data import build_kairo_data

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Kairo",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Hide all Streamlit chrome
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    #MainMenu, header, footer { display: none !important; }
    .stApp { padding: 0 !important; }
    .block-container { padding: 0 !important; max-width: 100% !important; }
    div[data-testid="stVerticalBlock"] { gap: 0 !important; }
    iframe { border: none !important; }
    /* hide "running" spinner overlay */
    .stSpinner { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Service initialisation (cached for the lifetime of the Streamlit session)
# ---------------------------------------------------------------------------

@st.cache_resource
def init_services():
    """Initialise ES, Gemini, and MongoDB.  Returns (es_manager, narrative_engine, tracker)."""
    try:
        from brain.config import Config

        def _secret(key: str, default: str = "") -> str:
            try:
                return st.secrets.get(key, os.getenv(key, getattr(Config, key, default) or default))
            except Exception:
                return os.getenv(key, getattr(Config, key, default) or default)

        demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"

        gemini_key = _secret("GEMINI_KEY")
        es_url      = _secret("ES_URL")

        if demo_mode:
            es_manager = None
            narrative_engine = NarrativeEngine(gemini_key) if gemini_key else None
            tracker = None
            return es_manager, narrative_engine, tracker

        if not es_url:
            raise ValueError("ES_URL not configured")
        if not gemini_key:
            raise ValueError("GEMINI_KEY not configured")

        es_username    = _secret("ES_USERNAME")
        es_password    = _secret("ES_PASSWORD")
        es_api_key_id  = _secret("ES_API_KEY_ID")
        mongo_uri      = _secret("MONGO_URI")
        mongo_db       = _secret("MONGO_DB") or "kairo"

        es_manager       = ElasticsearchManager(es_url, es_username, es_password, es_api_key_id)
        narrative_engine = NarrativeEngine(gemini_key)
        tracker          = NarrativeTracker(mongo_uri, mongo_db)

        return es_manager, narrative_engine, tracker

    except Exception as exc:
        logger.warning("init_services failed: %s", exc)
        return None, None, None


# ---------------------------------------------------------------------------
# Data building (cached for 5 minutes)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300)
def _cached_build_data(user_id: str, hours: int = 24) -> dict:
    """Fetch dune_context from ES and build kairo_data. Safe — always returns a dict."""
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
        from synthesize.kairo_data import _fallback_data
        return _fallback_data()


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

    base = str(Path(__file__).resolve().parent / "kairo_design")
    tweaks_panel_jsx  = _read(f"{base}/tweaks-panel.jsx")
    components_jsx    = _read(f"{base}/components.jsx")
    screen_morning_jsx = _read(f"{base}/screen-morning.jsx")
    screen_narrative_jsx = _read(f"{base}/screen-narrative.jsx")
    screen_history_jsx = _read(f"{base}/screen-history.jsx")
    screen_config_jsx  = _read(f"{base}/screen-config.jsx")
    app_jsx           = _read(f"{base}/app.jsx")

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
{app_jsx}
  </script>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# JSON encoder that handles datetime objects safely
# ---------------------------------------------------------------------------

class _KairoEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

es_manager, narrative_engine, tracker = init_services()
demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"

# ── Sidebar (collapsed by default) ──────────────────────────────────────────
user_id = st.sidebar.text_input("User ID", value="default")
hours_lookback = st.sidebar.slider("Hours to analyse", 1, 168, 24)

# ── Refresh / Run Detection button ──────────────────────────────────────────
col_btn, col_status = st.columns([1, 5])
with col_btn:
    run_detection = st.button("🔮 Refresh / Run Detection", use_container_width=True)

# If button pressed, run detection then clear the cache so data rebuilds
if run_detection:
    _cached_build_data.clear()
    if es_manager is not None and narrative_engine is not None:
        with col_status:
            with st.spinner("Fetching signals & running Gemini narrative analysis…"):
                try:
                    dune_context = es_manager.get_dune_signal_context(hours=hours_lookback)
                    signal_trend = es_manager.get_signal_trend(hours_per_bucket=24, num_buckets=3)
                    current_narratives = tracker.get_current_narratives(user_id, min_confidence=0.0) if tracker else []
                    # Richer summary for Gemini: includes prior evidence, momentum, hours_since_update
                    history_summary = tracker.get_narratives_summary(user_id) if tracker else []

                    def _parse_dt(val):
                        if isinstance(val, datetime):
                            return val.replace(tzinfo=val.tzinfo)
                        if isinstance(val, str):
                            try:
                                return datetime.fromisoformat(val.replace("Z", "+00:00"))
                            except Exception:
                                pass
                        return None

                    latest_ingested = max(
                        filter(None, (_parse_dt(doc.get("ingested_at")) for docs in dune_context.values() for doc in docs)),
                        default=None,
                    )
                    last_detected = max(
                        filter(None, (_parse_dt(n.get("detected_at")) for n in current_narratives)),
                        default=None,
                    )
                    has_new_data = (
                        latest_ingested is None
                        or last_detected is None
                        or latest_ingested.replace(tzinfo=None) > last_detected.replace(tzinfo=None)
                    )

                    if has_new_data or not current_narratives:
                        new_narratives = narrative_engine.detect_narratives(
                            dune_context=dune_context,
                            historical_narratives=history_summary,
                            signal_trend=signal_trend,
                        )
                        if new_narratives:
                            enriched = [
                                narrative_engine.enrich_narrative(n, previous_narratives=current_narratives)
                                for n in new_narratives
                            ]
                            if tracker:
                                tracker.save_narratives(enriched, user_id)
                                returned_ids = {n.get("narrative_id") for n in enriched}
                                tracker.mark_stale_narratives(returned_ids, user_id)
                    # force cache invalidation for fresh data
                    _cached_build_data.clear()
                    st.success(f"Detection complete — refreshing Kairo…")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Detection error: {exc}")
                    logger.exception("Detection failed")
    else:
        with col_status:
            st.info("Services not fully configured — showing available data.")

# ── Build data (cached 5 min) ────────────────────────────────────────────────
kairo_data = _cached_build_data(user_id, hours_lookback)

# ── Serialise to JSON ────────────────────────────────────────────────────────
try:
    data_json_str = json.dumps(kairo_data, cls=_KairoEncoder, ensure_ascii=False)
except Exception as exc:
    logger.exception("JSON serialisation failed: %s", exc)
    from synthesize.kairo_data import _fallback_data
    data_json_str = json.dumps(_fallback_data(), ensure_ascii=False)

# ── Build and render the Kairo HTML ─────────────────────────────────────────
html = build_kairo_html(data_json_str)
components.html(html, height=1400, scrolling=True)
