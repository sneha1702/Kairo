/* ============================================================
   Kairo — shared UI components
   ============================================================ */
const { useState, useRef, useEffect } = React;
const K = window.KAIRO;

/* ---- minimal line icons (functional UI glyphs) ---- */
function Icon({ name, size = 18, stroke = 1.6, style }) {
  const p = {
    width: size, height: size, viewBox: "0 0 24 24", fill: "none",
    stroke: "currentColor", strokeWidth: stroke, strokeLinecap: "round",
    strokeLinejoin: "round", style,
  };
  const paths = {
    sun:    <><circle cx="12" cy="12" r="4.2" /><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5 5l1.4 1.4M17.6 17.6L19 19M19 5l-1.4 1.4M6.4 17.6L5 19" /></>,
    today:  <><path d="M4 13.5 12 6l8 7.5" /><path d="M6 12v7h12v-7" /></>,
    narr:   <><path d="M5 5h14M5 12h14M5 19h9" /></>,
    history:<><circle cx="12" cy="12" r="8" /><path d="M12 8v4l2.5 1.5" /></>,
    watch:  <><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="2.4" /></>,
    brain:  <><path d="M9 4a3 3 0 0 0-3 3 3 3 0 0 0-1 5.8A3 3 0 0 0 9 18.5V4Z" /><path d="M15 4a3 3 0 0 1 3 3 3 3 0 0 1 1 5.8A3 3 0 0 1 15 18.5V4Z" /></>,
    scale:  <><path d="M12 4v16M6 20h12" /><path d="M12 6 5 9l3 4a3 3 0 0 1-6 0l3-4M12 6l7 3-3 4a3 3 0 0 0 6 0l-3-4" /></>,
    layers: <><path d="m12 4 8 4-8 4-8-4 8-4Z" /><path d="m4 12 8 4 8-4M4 16l8 4 8-4" /></>,
    drop:   <><path d="M12 3.5c3.5 4 5.5 6.6 5.5 9.5a5.5 5.5 0 0 1-11 0c0-2.9 2-5.5 5.5-9.5Z" /></>,
    spark:  <><path d="M12 3v5M12 16v5M3 12h5M16 12h5" /><path d="M6.5 6.5 9 9M15 15l2.5 2.5M17.5 6.5 15 9M9 15l-2.5 2.5" /></>,
    swap:   <><path d="M7 7h11l-3-3M17 17H6l3 3" /></>,
    arrowUp:<><path d="M12 19V6M6 11l6-6 6 6" /></>,
    arrowR: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
    dash:   <><path d="M6 12h12" /></>,
    chevron:<><path d="m6 9 6 6 6-6" /></>,
    spark2: <><path d="M11 3 4 13h6l-1 8 8-11h-6l1-7Z" /></>,
    dot:    <circle cx="12" cy="12" r="3.5" fill="currentColor" stroke="none" />,
    markets:<><path d="M4 20V14M9 20V8M14 20V12M19 20V4" /></>,
    user:   <><path d="M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z" /><path d="M4 20c0-3.3 3.6-6 8-6s8 2.7 8 6" /></>,
    logout: <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" /></>,
    book:   <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" /></>,
  };
  return <svg {...p}>{paths[name] || null}</svg>;
}

/* ---- Force tag (pill with icon) ---- */
function ForceTag({ id, size = "md" }) {
  const f = K.forces[id];
  if (!f) return null;
  const pad = size === "sm" ? "3px 9px 3px 7px" : "5px 12px 5px 9px";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      background: `var(--c-${f.color})`, color: `var(--c-${f.color}-ink)`,
      borderRadius: 99, padding: pad, fontSize: size === "sm" ? 12 : 13,
      fontWeight: 600, whiteSpace: "nowrap",
    }}>
      <Icon name={f.icon} size={size === "sm" ? 13 : 15} stroke={1.8} />
      {f.label}
    </span>
  );
}

/* ---- Asset chip ---- */
function Asset({ sym, tone = "default" }) {
  const styles = {
    default: { background: "var(--surface-2)", color: "var(--ink-2)", border: "1px solid var(--hairline)" },
    accent:  { background: "var(--accent-soft)", color: "var(--accent-ink)", border: "1px solid transparent" },
  };
  return (
    <span className="mono" style={{
      ...styles[tone], display: "inline-flex", alignItems: "center",
      borderRadius: 8, padding: "3px 9px", fontSize: 12.5, fontWeight: 600,
      letterSpacing: "0.01em",
    }}>{sym}</span>
  );
}

/* ---- Status badge (dot + word) ---- */
function StatusBadge({ status, size = "md" }) {
  const s = K.statuses[status];
  if (!s) return null;
  const dotColor = s.dot === "accent" ? "var(--accent)"
    : s.dot === "neutral" ? "var(--neutral)" : `var(--c-${s.dot}-ink)`;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 7,
      fontSize: size === "sm" ? 12.5 : 13.5, fontWeight: 600, color: "var(--ink-2)",
    }}>
      <span style={{
        width: 8, height: 8, borderRadius: 99, background: dotColor,
        boxShadow: `0 0 0 4px color-mix(in oklch, ${dotColor} 16%, transparent)`,
      }} />
      {s.label}
    </span>
  );
}

/* ---- directional sentiment marker (calm) ---- */
function Dir({ dir }) {
  const map = {
    up:   { name: "arrowUp", color: "var(--pos)" },
    flat: { name: "arrowR",  color: "var(--neutral)" },
    none: { name: "dash",    color: "var(--ink-4)" },
  };
  const m = map[dir] || map.flat;
  return (
    <span style={{
      display: "inline-grid", placeItems: "center", width: 26, height: 26,
      borderRadius: 8, background: "var(--surface-2)", color: m.color, flexShrink: 0,
    }}>
      <Icon name={m.name} size={15} stroke={2} />
    </span>
  );
}

/* ---- confidence pill ---- */
function Confidence({ level }) {
  const fill = level === "High" ? 3 : level === "Medium" ? 2 : 1;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
      <span style={{ display: "inline-flex", gap: 3 }}>
        {[0,1,2].map(i => (
          <span key={i} style={{
            width: 5, height: 13, borderRadius: 2,
            background: i < fill ? "var(--pos)" : "var(--hairline-strong)",
          }} />
        ))}
      </span>
      <span style={{ fontSize: 13.5, fontWeight: 600, color: "var(--ink-2)" }}>{level}</span>
    </span>
  );
}

/* ---- strength curve sparkline ---- */
function StrengthCurve({ data, w = 560, h = 120, max = 10 }) {
  const pad = 6;
  const n = data.length;
  const xs = i => pad + (i / (n - 1)) * (w - pad * 2);
  const ys = v => h - pad - (v / max) * (h - pad * 2);
  const line = data.map((v, i) => `${i === 0 ? "M" : "L"}${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(" ");
  const area = `${line} L${xs(n-1).toFixed(1)},${h} L${xs(0).toFixed(1)},${h} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none" style={{ display: "block" }}>
      <defs>
        <linearGradient id="kairoCurve" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"  stopColor="var(--accent)" stopOpacity="0.20" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#kairoCurve)" />
      <path d={line} fill="none" stroke="var(--accent)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={xs(n-1)} cy={ys(data[n-1])} r="4.5" fill="var(--accent)" stroke="var(--surface)" strokeWidth="2.5" />
    </svg>
  );
}

/* ---- "Explain like I'm busy" expander ---- */
function ExplainToggle({ open, onToggle }) {
  return (
    <button onClick={onToggle} style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      color: "var(--accent-ink)", fontSize: 13.5, fontWeight: 600, padding: "6px 0", whiteSpace: "nowrap",
    }}>
      {open ? "Show less" : "Explain like I'm busy"}
      <Icon name="chevron" size={15} stroke={2}
        style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform 0.25s" }} />
    </button>
  );
}

/* ---- section eyebrow row ---- */
function CardLabel({ icon, children, right }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {icon && <span style={{ color: "var(--ink-3)" }}><Icon name={icon} size={15} stroke={1.8} /></span>}
        <span className="eyebrow">{children}</span>
      </div>
      {right}
    </div>
  );
}

Object.assign(window, {
  Icon, ForceTag, Asset, StatusBadge, Dir, Confidence, StrengthCurve, ExplainToggle, CardLabel,
});
