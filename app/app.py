"""
HTML builder and JSON encoder for the Kairo React SPA.
No web-framework dependencies — called by web/views.py.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JSON encoder that handles datetime objects
# ---------------------------------------------------------------------------

class _KairoEncoder(json.JSONEncoder):
    def default(self, obj):  # type: ignore
        if isinstance(obj, datetime):
            return obj.isoformat()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


# ---------------------------------------------------------------------------
# HTML builder — inlines all design tokens, layout CSS, and JSX source
# ---------------------------------------------------------------------------

def build_kairo_html(data_json: str) -> str:
    """Return the complete Kairo HTML with data injected as window.KAIRO."""

    styles_css = r"""/* ============================================================
   Kairo — design tokens & base styles
   ============================================================ */

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
  --c-sage:   oklch(0.90 0.050 150);   --c-sage-ink:   oklch(0.50 0.085 150);
  --c-denim:  oklch(0.90 0.050 250);   --c-denim-ink:  oklch(0.50 0.090 252);
  --c-lav:    oklch(0.90 0.050 300);   --c-lav-ink:    oklch(0.50 0.090 300);
  --c-peach:  oklch(0.90 0.050 55);    --c-peach-ink:  oklch(0.52 0.090 50);
  --c-rose:   oklch(0.90 0.050 18);    --c-rose-ink:   oklch(0.52 0.095 22);
  --c-teal:   oklch(0.90 0.050 195);   --c-teal-ink:   oklch(0.50 0.080 198);
  --pos:      oklch(0.56 0.085 155);
  --neutral:  oklch(0.62 0.010 70);
  --font-sans: "Hanken Grotesk", ui-sans-serif, system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SF Mono", monospace;
  --r-sm: 10px; --r-md: 16px; --r-lg: 22px; --r-xl: 28px;
  --shadow-card: 0 1px 2px oklch(0.5 0.02 60 / 0.05), 0 6px 22px oklch(0.5 0.02 60 / 0.06);
  --shadow-soft: 0 1px 2px oklch(0.5 0.02 60 / 0.04);
  --gap: 18px; --card-pad: 26px; --col: 660px;
}
[data-density="compact"] { --gap: 12px; --card-pad: 20px; }
[data-density="comfy"]   { --gap: 24px; --card-pad: 32px; }

* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0; height: 100%; overflow: hidden;
  background: var(--paper); color: var(--ink-2);
  font-family: var(--font-sans); font-size: 16px; line-height: 1.55;
  -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;
}
h1, h2, h3, h4 { color: var(--ink); font-weight: 700; line-height: 1.15; margin: 0; letter-spacing: -0.012em; text-wrap: balance; }
p { margin: 0; text-wrap: pretty; }
a { color: inherit; text-decoration: none; }
button { font-family: inherit; cursor: pointer; border: none; background: none; }
.mono { font-family: var(--font-mono); font-feature-settings: "tnum" 1; letter-spacing: -0.01em; }
.eyebrow { font-family: var(--font-mono); font-size: 11px; font-weight: 500; letter-spacing: 0.10em; text-transform: uppercase; color: var(--ink-3); }
::selection { background: var(--accent-soft); }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: var(--hairline-strong); border-radius: 99px; border: 3px solid var(--paper); }
::-webkit-scrollbar-track { background: transparent; }
.card { background: var(--surface); border: 1px solid var(--hairline); border-radius: var(--r-lg); box-shadow: var(--shadow-card); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
@keyframes kairoFade {
  from { transform: translateY(9px); }
  to   { transform: translateY(0); }
}
@media (prefers-reduced-motion: no-preference) {
  .screen-enter > * { animation: kairoFade 0.5s cubic-bezier(0.22, 1, 0.36, 1); }
}"""

    layout_css = r"""
    .kairo-app { display: flex; height: 100vh; overflow: hidden; }
    .kairo-rail {
      width: 244px; flex-shrink: 0; height: 100vh; overflow-y: auto;
      padding: 26px 18px; display: flex; flex-direction: column;
      border-right: 1px solid var(--hairline);
      background: color-mix(in oklch, var(--paper) 60%, var(--surface));
    }
    .kairo-navitems { display: flex; flex-direction: column; gap: 4px; }
    .kairo-rail-foot { margin-top: auto; padding-top: 24px; }
    .kairo-main {
      flex: 1; min-width: 0; height: 100vh; overflow-y: auto;
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
        backdrop-filter: blur(8px); position: sticky; top: 0;
      }
      .kairo-logo { padding: 0 14px 0 2px !important; }
      .kairo-navitems { flex-direction: row; margin-left: auto; gap: 4px; }
      .kairo-rail-foot { display: none; }
      .kairo-main { height: auto; overflow-y: visible; padding: 30px 18px 60px; }
    }
    @media (max-width: 480px) {
      .kairo-navitems button span:last-child { display: none; }
    }
    .kairo-loading {
      min-height: 100vh; display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 18px;
      background: var(--paper); font-family: var(--font-sans);
    }
    .kairo-loading-logo { display: flex; align-items: center; gap: 11px; margin-bottom: 4px; }
    .kairo-loading-dot {
      width: 30px; height: 30px; border-radius: 9px;
      background: var(--ink); display: grid; place-items: center;
    }
    .kairo-loading-dot-inner {
      width: 13px; height: 13px; border-radius: 99px; background: var(--accent);
      animation: kairo-pulse 1.5s ease-in-out infinite;
    }
    .kairo-loading-text { font-size: 14.5px; color: var(--ink-3); letter-spacing: 0.01em; }
    @keyframes kairo-pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50%       { opacity: 0.4; transform: scale(0.78); }
    }"""

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

    return f"""<!DOCTYPE html>
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
</body>
</html>"""
