/* ============================================================
   Kairo — Narrative History ("Pattern Memory")
   How today's story compares to every prior occurrence
   ============================================================ */
const K = window.KAIRO;
let Icon, ForceTag;

function CycleBar({ peak, current, weeks }) {
  // a small horizontal "build & fade" curve sized by duration & peak
  const w = 100, h = 40, max = 10;
  const rise = 0.42; // peak at 42% along
  const pts = [];
  const n = 32;
  for (let i = 0; i < n; i++) {
    const x = i / (n - 1);
    // asymmetric hump: faster fade for shorter (speculative) cycles handled by caller via peak
    let v;
    if (x <= rise) v = peak * Math.pow(x / rise, 0.75);
    else v = peak * Math.pow(1 - (x - rise) / (1 - rise), current ? 0.55 : 0.9);
    pts.push([6 + x * (w - 12), h - 4 - (v / max) * (h - 8)]);
  }
  const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${line} L${(w-6)},${h} L6,${h} Z`;
  const col = current ? "var(--accent)" : "var(--ink-3)";
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none" style={{ display: "block", overflow: "visible" }}>
      <path d={area} fill={current ? "var(--accent-soft)" : "var(--surface-2)"} opacity={current ? 0.7 : 1} />
      <path d={line} fill="none" stroke={col} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CycleRow({ c }) {
  return (
    <article className="card" style={{
      padding: "var(--card-pad)",
      borderColor: c.current ? "color-mix(in oklch, var(--accent) 38%, var(--hairline))" : "var(--hairline)",
      boxShadow: c.current ? "0 0 0 2px var(--accent-soft), var(--shadow-card)" : "var(--shadow-soft)",
      background: c.current ? "linear-gradient(180deg, color-mix(in oklch, var(--accent-soft) 50%, var(--surface)) 0%, var(--surface) 50%)" : "var(--surface)",
    }}>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1.1fr) minmax(160px, 0.9fr)", gap: 24, alignItems: "center" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 10 }}>
            <h3 style={{ fontSize: 19, fontWeight: 800 }}>{c.name}</h3>
            {c.current && <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
              color: "var(--accent-ink)", background: "var(--accent-soft)", padding: "3px 9px", borderRadius: 99 }}>Now</span>}
            <span className="mono" style={{ fontSize: 13, color: "var(--ink-3)" }}>{c.span}</span>
          </div>
          <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
            <ForceTag id={c.force} size="sm" />
            <span style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink-2)", background: "var(--surface-2)",
              borderRadius: 99, padding: "4px 11px", border: "1px solid var(--hairline)" }}>{c.kind}</span>
          </div>
          <p style={{ fontSize: 15, color: "var(--ink-2)", lineHeight: 1.6, maxWidth: "42ch" }}>{c.note}</p>
        </div>
        <div>
          <CycleBar peak={c.peak} current={c.current} weeks={c.durationWeeks} />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10 }}>
            <Stat label="Peak strength" value={c.peak.toFixed(1)} accent={c.current} />
            <Stat label="Duration" value={`${c.durationWeeks} wk`} accent={c.current} align="right" />
          </div>
        </div>
      </div>
    </article>
  );
}

function Stat({ label, value, accent, align }) {
  return (
    <div style={{ textAlign: align || "left" }}>
      <div className="eyebrow" style={{ marginBottom: 4 }}>{label}</div>
      <div className="mono" style={{ fontSize: 17, fontWeight: 700, color: accent ? "var(--accent-ink)" : "var(--ink)" }}>{value}</div>
    </div>
  );
}

function NarrativeHistory() {
  ({ Icon, ForceTag } = window);
  const h = K.history;
  return (
    <div className="screen-enter" style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
      <header>
        <div style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--ink-3)", marginBottom: 12 }}>
          <Icon name="history" size={18} stroke={1.8} />
          <span className="eyebrow">Pattern memory</span>
        </div>
        <h1 style={{ fontSize: "clamp(28px, 3.6vw, 38px)", fontWeight: 800, letterSpacing: "-0.025em" }}>{h.title}</h1>
        <p style={{ fontSize: 18, color: "var(--ink-2)", marginTop: 12, maxWidth: "52ch" }}>{h.subtitle}</p>
      </header>

      {h.cycles && h.cycles.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--gap)", marginTop: 4 }}>
          {h.cycles.map(c => <CycleRow key={c.name} c={c} />)}
        </div>
      ) : (
        <div style={{
          padding: "48px 32px", textAlign: "center", background: "var(--surface)",
          border: "1px dashed var(--hairline-strong)", borderRadius: "var(--r-lg)",
        }}>
          <p style={{ fontSize: 15, color: "var(--ink-3)", maxWidth: "38ch", margin: "0 auto" }}>
            No historical cycles yet. As Kairo detects more narratives over time, pattern comparisons will appear here.
          </p>
        </div>
      )}

      <article className="card" style={{
        padding: "calc(var(--card-pad) + 2px)", marginTop: 4,
        background: "var(--ink)", borderColor: "var(--ink)", color: "var(--paper)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 14, opacity: 0.7 }}>
          <Icon name="spark2" size={16} stroke={1.8} />
          <span className="eyebrow" style={{ color: "var(--paper)", opacity: 0.8 }}>What the pattern tells us</span>
        </div>
        <p style={{ fontSize: "clamp(18px, 2.2vw, 22px)", lineHeight: 1.5, fontWeight: 600,
          color: "var(--paper)", letterSpacing: "-0.01em", maxWidth: "46ch", textWrap: "balance" }}>
          {h.interpretation}
        </p>
      </article>
    </div>
  );
}

Object.assign(window, { NarrativeHistory });
