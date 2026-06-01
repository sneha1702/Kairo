import streamlit as st
import streamlit.components.v1 as components
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
# Global styles — hide Streamlit chrome + apply Kairo design tokens everywhere
# ---------------------------------------------------------------------------
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
    /* Eliminate default Streamlit vertical gaps so the iframe sits flush */
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
    /* Strip all padding from tab panels — admin uses columns for its own width */
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

# Set autocomplete="off" on Streamlit text inputs so Chrome stops warning about
# the empty autocomplete attribute. Streamlit strips <script> from st.markdown,
# so reach into the parent DOM from a zero-height component iframe.
components.html(
    """
    <script>
    (function tick() {
      try {
        var doc = window.parent.document;
        doc.querySelectorAll('.stTextInput input').forEach(function (el) {
          if (el.getAttribute('autocomplete') !== 'off') el.setAttribute('autocomplete', 'off');
        });
      } catch (e) {}
      setTimeout(tick, 600);
    })();
    </script>
    """,
    height=0,
)

# ---------------------------------------------------------------------------
# Service initialisation (cached for the lifetime of the Streamlit session)
# ---------------------------------------------------------------------------

@st.cache_resource
def init_services():
    """Initialise ES, Gemini, and MongoDB.  Returns (es_manager, narrative_engine, tracker)."""
    try:
        from config.config import Config

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
from app.ingestion.dune_pipeline import build_pipeline as _build_pipeline

es_manager, narrative_engine, tracker = init_services()


# ---------------------------------------------------------------------------
# Fragment: entire admin panel.
# Wrapping everything in ONE fragment means no interaction inside the admin
# tab ever causes a full-page re-run — the Kairo iframe is never touched.
# Only explicit st.rerun() calls (after data-changing operations) refresh
# the whole page so the Kairo tab picks up new data.
# ---------------------------------------------------------------------------

_WINDOW_PRESETS: list[tuple[str, int]] = [
    ("2 hours",           2),
    ("4 hours (default)", 4),
    ("6 hours",           6),
    ("12 hours",          12),
    ("24 hours / 1 day",  24),
    ("48 hours / 2 days", 48),
    ("1 week",            168),
    ("1 month",           720),
    ("3 months",          2160),
    ("6 months",          4380),
    ("1 year",            8760),
]

@st.fragment
def _admin_panel() -> None:
    _es, _engine, _tracker = init_services()

    # Constrain admin content width without touching the Kairo tab panel
    col, _ = st.columns([5, 2])
    with col:
        _admin_panel_content(_es, _engine, _tracker)


def _admin_panel_content(_es, _engine, _tracker) -> None:
    # ── Detection Settings ────────────────────────────────────────────────────
    st.subheader("Detection Settings")
    st.text_input("User ID", value="default", key="admin_user_id")
    st.slider("Hours to analyse", 1, 168, min(168, _Cfg.DUNE_QUERY_WINDOW_HOURS), key="admin_hours_lookback")

    st.divider()

    # ── Dune Ingestion Settings ───────────────────────────────────────────────
    st.subheader("Dune Ingestion Settings")

    _preset_labels = [p[0] for p in _WINDOW_PRESETS]
    _preset_hours  = [p[1] for p in _WINDOW_PRESETS]
    _preset_map    = dict(_WINDOW_PRESETS)

    current_hours = _Cfg.DUNE_QUERY_WINDOW_HOURS
    current_label = next((lbl for lbl, h in _WINDOW_PRESETS if h == current_hours),
                         f"{current_hours}h (custom)")
    st.caption(f"Active query window: **{current_label}** ({current_hours}h)")

    default_idx = _preset_hours.index(current_hours) if current_hours in _preset_hours else 1
    st.selectbox(
        "Query window — how far back each Dune query looks",
        options=_preset_labels,
        index=default_idx,
        key="dune_window_select",
    )

    st.checkbox(
        "Fetch fresh data from Dune immediately after saving",
        value=True,
        key="fetch_after_save",
        help="Runs all 8 Dune queries with the new window and stores results in Elasticsearch.",
    )

    if st.button("Save & Apply", use_container_width=True, key="save_dune_window"):
        _selected_window = st.session_state.get("dune_window_select", "4 hours (default)")
        _selected_hours  = _preset_map.get(_selected_window, 4)
        try:
            _Cfg.set_dune_query_window(_selected_hours)
            st.success(f"Query window set to **{_selected_window}** ({_selected_hours}h).")

            if st.session_state.get("fetch_after_save", True):
                status = st.empty()
                progress = st.progress(0, text="Connecting to Dune…")
                try:
                    progress.progress(10, text="Running Dune pipeline…")
                    pipeline = _build_pipeline()
                    progress.progress(40, text="Fetching on-chain data…")
                    results  = pipeline.run_all()
                    n_ok   = sum(1 for r in results.values() if r.success)
                    n_fail = sum(1 for r in results.values() if not r.success)
                    _cached_build_data.clear()
                    progress.progress(100, text="Done.")
                    if n_fail:
                        failed_names = [r.query_name for r in results.values() if not r.success]
                        status.warning(f"Ingestion: {n_ok} succeeded, {n_fail} failed: {failed_names}")
                    else:
                        total_rows = sum(r.rows_fetched for r in results.values())
                        status.success(f"Ingested {total_rows:,} rows across {n_ok} queries.")
                    st.rerun()
                except Exception as exc:
                    progress.empty()
                    st.error(f"Dune ingestion failed: {exc}")
                    logger.exception("Dune ingestion failed from admin panel")
        except Exception as exc:
            st.error(f"Failed to save config: {exc}")

    st.divider()

    # ── Run Detection ─────────────────────────────────────────────────────────
    st.subheader("Run Detection")
    if st.button("🔮 Run Detection", use_container_width=True, key="run_detection"):
        _user_id = st.session_state.get("admin_user_id", "default")
        _hours   = st.session_state.get("admin_hours_lookback", _Cfg.DUNE_QUERY_WINDOW_HOURS)

        if _es is not None and _engine is not None:
            status   = st.empty()
            progress = st.progress(0, text="Starting…")
            try:
                progress.progress(10, text="Fetching Elasticsearch signals…")
                dune_context = _es.get_dune_signal_context(hours=_hours)

                progress.progress(25, text="Fetching signal trend…")
                signal_trend = _es.get_signal_trend(hours_per_bucket=24, num_buckets=3)

                progress.progress(35, text="Loading existing narratives from MongoDB…")
                current_narratives = _tracker.get_current_narratives(_user_id, min_confidence=0.0) if _tracker else []
                history_summary    = _tracker.get_narratives_summary(_user_id) if _tracker else []

                progress.progress(50, text="Running Gemini narrative detection…")
                new_narratives = _engine.detect_narratives(
                    dune_context=dune_context,
                    historical_narratives=history_summary,
                    signal_trend=signal_trend,
                )

                enriched = []
                if new_narratives:
                    for i, n in enumerate(new_narratives):
                        pct = 60 + int(30 * (i + 1) / len(new_narratives))
                        progress.progress(pct, text=f"Enriching narrative {i + 1}/{len(new_narratives)}…")
                        enriched.append(_engine.enrich_narrative(n, previous_narratives=current_narratives))

                    if _tracker:
                        progress.progress(92, text="Saving to MongoDB…")
                        _tracker.save_narratives(enriched, _user_id)
                        returned_ids = {n.get("narrative_id") for n in enriched}
                        _tracker.mark_stale_narratives(returned_ids, _user_id)

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
        else:
            st.info("Services not fully configured — showing available data.")

    st.divider()

    # ── Service Status ────────────────────────────────────────────────────────
    st.subheader("Service Status")
    st.write("Elasticsearch:",    "✅ connected" if _es      is not None else "❌ not connected")
    st.write("Narrative Engine:", "✅ ready"     if _engine  is not None else "❌ not ready")
    st.write("MongoDB Tracker:",  "✅ connected" if _tracker is not None else "❌ not connected")


# ── Two-tab layout ────────────────────────────────────────────────────────────
tab_kairo, tab_admin = st.tabs(["Kairo", "⚙ Admin"])

with tab_admin:
    _admin_panel()

# ── Kairo tab — iframe only ───────────────────────────────────────────────────
with tab_kairo:
    user_id        = st.session_state.get("admin_user_id",      "default")
    hours_lookback = st.session_state.get("admin_hours_lookback", 24)

    kairo_data = _cached_build_data(user_id, hours_lookback)
    kairo_data.setdefault("config", {})["dune_query_window_hours"] = _Cfg.DUNE_QUERY_WINDOW_HOURS

    try:
        data_json_str = json.dumps(kairo_data, cls=_KairoEncoder, ensure_ascii=False)
    except Exception as exc:
        logger.exception("JSON serialisation failed: %s", exc)
        from app.synthesize.kairo_data import _empty_data
        data_json_str = json.dumps(_empty_data(), ensure_ascii=False)

    html = build_kairo_html(data_json_str)
    components.html(html, height=1400, scrolling=True)
