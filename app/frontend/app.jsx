/* ============================================================
   Kairo — app shell, navigation, tweaks
   ============================================================ */
const { useState, useEffect } = React;
let Icon, MorningBrief, NarrativeTracker, NarrativeHistory, ConfigScreen, CryptoMarkets, ProfileScreen;
let useTweaks, TweaksPanel, TweakSection, TweakRadio, TweakColor;

const NAV = [
  { id: "today",   label: "Today",        icon: "today" },
  { id: "narr",    label: "Narratives",   icon: "narr" },
  { id: "history", label: "History",      icon: "history" },
  { id: "markets", label: "Markets",      icon: "markets" },
  { id: "config",  label: "Subscription", icon: "watch" },
  { id: "profile", label: "Profile",      icon: "user"   },
  { id: "logout",  label: "Sign out",     icon: "logout", action: "logout" },
];

/* accent palettes: hex swatch -> oklch var set */
const ACCENTS = {
  "#c46a43": { accent: "oklch(0.64 0.124 42)",  soft: "oklch(0.92 0.045 50)",  ink: "oklch(0.46 0.115 40)" },  // terracotta
  "#6f9a7f": { accent: "oklch(0.61 0.072 150)", soft: "oklch(0.925 0.034 150)", ink: "oklch(0.45 0.068 150)" }, // sage
  "#5f7fc0": { accent: "oklch(0.59 0.090 252)", soft: "oklch(0.925 0.040 252)", ink: "oklch(0.46 0.090 252)" }, // denim
};
const FONTS = {
  "Hanken Grotesk": '"Hanken Grotesk", ui-sans-serif, system-ui, sans-serif',
  "Mulish": '"Mulish", ui-sans-serif, system-ui, sans-serif',
};

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "morningLayout": "editorial",
  "trackerTreatment": "timeline",
  "accent": "#c46a43",
  "font": "Hanken Grotesk",
  "density": "regular"
}/*EDITMODE-END*/;

function Logo() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
      <span style={{
        position: "relative", width: 30, height: 30, borderRadius: 9,
        background: "var(--ink)", display: "grid", placeItems: "center", flexShrink: 0,
      }}>
        <span style={{ width: 13, height: 13, borderRadius: 99,
          background: "var(--accent)", boxShadow: "0 0 0 3px color-mix(in oklch, var(--accent) 30%, transparent)" }} />
      </span>
      <span style={{ fontSize: 21, fontWeight: 800, letterSpacing: "-0.03em", color: "var(--ink)" }}>Kairo</span>
    </div>
  );
}

function handleLogout() {
  try {
    const url = new URL(window.top.location.href);
    url.searchParams.set("kairo_action", "logout");
    window.top.location.href = url.toString();
  } catch (_) {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("kairo_action", "logout");
      window.location.href = url.toString();
    } catch (__) {}
  }
}

function Sidebar({ view, setView }) {
  return (
    <nav className="kairo-rail">
      <div style={{ padding: "4px 4px 28px" }} className="kairo-logo"><Logo /></div>
      <div className="kairo-navitems">
        {NAV.map(n => {
          const isLogout = n.action === "logout";
          const active = !isLogout && view === n.id;
          return (
            <button key={n.id} onClick={() => isLogout ? handleLogout() : setView(n.id)} style={{
              display: "flex", alignItems: "center", gap: 12, padding: "11px 13px",
              borderRadius: 12,
              color: isLogout ? "var(--ink-4)" : active ? "var(--ink)" : "var(--ink-3)",
              background: active ? "var(--surface)" : "transparent",
              boxShadow: active ? "var(--shadow-soft)" : "none",
              border: active ? "1px solid var(--hairline)" : "1px solid transparent",
              fontSize: 15, fontWeight: 600, transition: "color 0.15s, background 0.15s",
              marginTop: isLogout ? "auto" : undefined,
            }}
            onMouseOver={e => { if (isLogout) e.currentTarget.style.color = "var(--ink-2)"; }}
            onMouseOut={e => { if (isLogout) e.currentTarget.style.color = "var(--ink-4)"; }}
            >
              <Icon name={n.icon} size={19} stroke={1.8} style={{ color: active ? "var(--accent-ink)" : "inherit" }} />
              {n.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [view, setView] = useState(() => {
    return localStorage.getItem("kairo-view") || "today";
  });
  const [activeNarr, setActiveNarr] = useState(() => {
    const first = window.KAIRO && window.KAIRO.narratives && window.KAIRO.narratives[0];
    return first ? first.id : "l2-rotation";
  });

  useEffect(() => { localStorage.setItem("kairo-view", view); }, [view]);

  // apply theme tweaks to :root
  useEffect(() => {
    const r = document.documentElement;
    const a = ACCENTS[t.accent] || ACCENTS["#c46a43"];
    r.style.setProperty("--accent", a.accent);
    r.style.setProperty("--accent-soft", a.soft);
    r.style.setProperty("--accent-ink", a.ink);
    r.style.setProperty("--font-sans", FONTS[t.font] || FONTS["Hanken Grotesk"]);
    r.setAttribute("data-density", t.density);
  }, [t.accent, t.font, t.density]);

  const openNarrative = (id) => { setActiveNarr(id); setView("narr"); };

  let screen;
  if (view === "today") screen = <MorningBrief layout={t.morningLayout} onOpenNarrative={openNarrative} />;
  else if (view === "narr") screen = <NarrativeTracker treatment={t.trackerTreatment} activeId={activeNarr} onSelect={setActiveNarr} />;
  else if (view === "history") screen = <NarrativeHistory />;
  else if (view === "markets") screen = <CryptoMarkets />;
  else if (view === "profile") screen = ProfileScreen ? <ProfileScreen /> : <ConfigScreen />;
  else screen = <ConfigScreen />;

  const username = (window.KAIRO?.user?.first_name || window.KAIRO?.user?.username || "").trim();

  return (
    <div className="kairo-app">
      <Sidebar view={view} setView={setView} />
      <main className="kairo-main" style={{ position: "relative" }}>
        {username && (
          <div style={{
            position: "absolute", top: 18, right: 32,
            fontSize: 13, fontWeight: 600, color: "var(--accent-ink)",
            letterSpacing: "-0.01em",
          }}>
            Hey {username} <span style={{ color: "var(--ink-4)", fontWeight: 500 }}>(signed in)</span>
          </div>
        )}
        <div className="kairo-col" key={view}>{screen}</div>
      </main>

      <TweaksPanel>
        <TweakSection label="Layout" />
        <TweakRadio label="Morning Brief" value={t.morningLayout}
          options={["editorial", "cards", "compact"]}
          onChange={v => setTweak("morningLayout", v)} />
        <TweakRadio label="Narrative view" value={t.trackerTreatment}
          options={["timeline", "arc"]}
          onChange={v => setTweak("trackerTreatment", v)} />
        <TweakRadio label="Density" value={t.density}
          options={["compact", "regular", "comfy"]}
          onChange={v => setTweak("density", v)} />

        <TweakSection label="Theme" />
        <TweakColor label="Accent" value={t.accent}
          options={["#c46a43", "#6f9a7f", "#5f7fc0"]}
          onChange={v => setTweak("accent", v)} />
        <TweakRadio label="Typeface" value={t.font}
          options={["Hanken Grotesk", "Mulish"]}
          onChange={v => setTweak("font", v)} />
      </TweaksPanel>
    </div>
  );
}

/* wait for all babel src modules to finish loading before first render —
   type=text/babel src scripts can resolve out of order, so gate the mount */
function kairoMount(attempts) {
  attempts = attempts || 0;
  const ready = window.MorningBrief && window.NarrativeTracker && window.NarrativeHistory
    && window.ConfigScreen && window.CryptoMarkets
    && window.useTweaks && window.TweaksPanel && window.Icon && window.KAIRO;
  if (!ready) {
    if (attempts > 400) {
      const root = document.getElementById("root");
      if (root) root.innerHTML = '<div style="padding:40px 32px;font-family:ui-sans-serif,system-ui,sans-serif;color:#c46a43;font-size:15px">Kairo failed to load — please refresh the page.</div>';
      return;
    }
    setTimeout(() => kairoMount(attempts + 1), 25);
    return;
  }
  ({ Icon, MorningBrief, NarrativeTracker, NarrativeHistory, ConfigScreen, CryptoMarkets,
     ProfileScreen, useTweaks, TweaksPanel, TweakSection, TweakRadio, TweakColor } = window);
  ReactDOM.createRoot(document.getElementById("root")).render(<App />);
}
kairoMount(0);
