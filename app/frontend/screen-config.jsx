/* ============================================================
   Kairo — Configuration / Plans screen
   ============================================================ */
let Icon;

const WINDOW_PRESETS = [
  { label: "2 hours",   hours: 2 },
  { label: "4 hours",   hours: 4 },
  { label: "6 hours",   hours: 6 },
  { label: "12 hours",  hours: 12 },
  { label: "1 day",     hours: 24 },
  { label: "2 days",    hours: 48 },
  { label: "1 week",    hours: 168 },
  { label: "1 month",   hours: 720 },
  { label: "3 months",  hours: 2160 },
  { label: "6 months",  hours: 4380 },
  { label: "1 year",    hours: 8760 },
];

function hoursToLabel(h) {
  const match = WINDOW_PRESETS.find(p => p.hours === h);
  return match ? match.label : `${h}h`;
}

function DataRangeAdmin() {
  const configuredHours = window.KAIRO?.config?.dune_query_window_hours ?? 4;

  return (
    <article className="card" style={{ padding: "var(--card-pad)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 16 }}>
        <Icon name="spark2" size={16} stroke={1.8} />
        <span className="eyebrow">Admin — Data Range</span>
      </div>

      <div style={{ marginBottom: 18 }}>
        <div style={{ fontSize: 13.5, color: "var(--ink-3)", marginBottom: 6 }}>
          Current ingestion window
        </div>
        <div style={{
          display: "inline-flex", alignItems: "center", gap: 8,
          padding: "8px 16px", borderRadius: "var(--r-sm)",
          background: "var(--accent-soft)", border: "1px solid color-mix(in oklch, var(--accent) 30%, var(--hairline))",
        }}>
          <span style={{ fontSize: 17, fontWeight: 700, color: "var(--accent-ink)" }}>
            {hoursToLabel(configuredHours)}
          </span>
          <span style={{ fontSize: 13, color: "var(--ink-3)" }}>
            ({configuredHours}h)
          </span>
        </div>
      </div>

      <div style={{ fontSize: 13.5, color: "var(--ink-3)", marginBottom: 10 }}>
        Available presets
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 18 }}>
        {WINDOW_PRESETS.map(p => {
          const active = p.hours === configuredHours;
          return (
            <span key={p.hours} style={{
              padding: "5px 13px", borderRadius: "var(--r-sm)", fontSize: 13.5, fontWeight: 600,
              background: active ? "var(--accent)" : "var(--surface-2)",
              color: active ? "var(--paper)" : "var(--ink-2)",
              border: `1px solid ${active ? "var(--accent)" : "var(--hairline)"}`,
            }}>
              {p.label}
            </span>
          );
        })}
      </div>

      <p style={{ fontSize: 13.5, color: "var(--ink-3)", lineHeight: 1.6 }}>
        To change the query window, use the <strong style={{ color: "var(--ink-2)" }}>Admin Panel → Dune Ingestion Settings</strong> in
        the Streamlit interface, or set the <code style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>DUNE_QUERY_WINDOW_HOURS</code> env var.
        Restart the ingestion pipeline after saving.
      </p>
    </article>
  );
}

const PLANS = [
  {
    id: "free",
    name: "Free",
    price: "$0",
    period: "forever",
    refresh: "Every 24 hours",
    features: [
      "Daily narrative briefing",
      "Up to 3 tracked assets",
      "Basic signal summary",
      "Historical pattern access",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: "$29",
    period: "per month",
    refresh: "Every 4 hours",
    highlight: true,
    features: [
      "4-hour narrative updates",
      "Up to 10 tracked assets",
      "Full signal breakdown",
      "Force tracker & episodes",
      "Email digest",
    ],
  },
  {
    id: "premium",
    name: "Premium",
    price: "$99",
    period: "per month",
    refresh: "Real-time",
    dark: true,
    features: [
      "Real-time narrative tracking",
      "Unlimited assets",
      "Push notifications",
      "Alert thresholds",
      "API access",
      "Priority support",
    ],
  },
];

function PlanCard({ plan, selected, onSelect }) {
  const dark = !!plan.dark;
  return (
    <article
      className="card"
      onClick={() => onSelect(plan.id)}
      style={{
        padding: "var(--card-pad)", cursor: "pointer",
        background: dark
          ? "var(--ink)"
          : selected
            ? "linear-gradient(180deg, color-mix(in oklch, var(--accent-soft) 80%, var(--surface)) 0%, var(--surface) 60%)"
            : "var(--surface)",
        borderColor: dark
          ? "var(--ink)"
          : selected
            ? "color-mix(in oklch, var(--accent) 40%, var(--hairline))"
            : "var(--hairline)",
        boxShadow: selected
          ? "0 0 0 2px var(--accent-soft), var(--shadow-card)"
          : "var(--shadow-soft)",
        color: dark ? "var(--paper)" : "var(--ink)",
        display: "flex", flexDirection: "column",
      }}>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <h3 style={{ fontSize: 22, fontWeight: 800, marginBottom: 6,
            color: dark ? "var(--paper)" : "var(--ink)" }}>{plan.name}</h3>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
            <span className="mono" style={{ fontSize: 28, fontWeight: 700,
              color: dark ? "var(--paper)" : "var(--ink)" }}>{plan.price}</span>
            <span style={{ fontSize: 13, color: dark ? "oklch(0.68 0.01 80)" : "var(--ink-3)" }}>{plan.period}</span>
          </div>
        </div>
        {selected && (
          <span style={{
            fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
            color: dark ? "var(--ink)" : "var(--accent-ink)",
            background: dark ? "var(--accent-soft)" : "var(--accent-soft)",
            padding: "3px 9px", borderRadius: 99,
          }}>Active</span>
        )}
      </div>

      {/* Refresh cadence */}
      <div style={{
        marginBottom: 20, padding: "11px 14px", borderRadius: "var(--r-sm)",
        background: dark ? "rgba(255,255,255,0.08)" : "var(--surface-2)",
      }}>
        <div className="eyebrow" style={{ color: dark ? "oklch(0.65 0.01 80)" : "var(--ink-3)", marginBottom: 4 }}>
          Narrative refresh
        </div>
        <div style={{ fontSize: 16, fontWeight: 700, color: dark ? "var(--paper)" : "var(--ink)" }}>
          {plan.refresh}
        </div>
      </div>

      {/* Features */}
      <div style={{ display: "flex", flexDirection: "column", gap: 9, flex: 1 }}>
        {plan.features.map(f => (
          <div key={f} style={{
            display: "flex", alignItems: "center", gap: 10,
            fontSize: 14.5, color: dark ? "oklch(0.85 0.01 80)" : "var(--ink-2)",
          }}>
            <span style={{
              width: 6, height: 6, borderRadius: 99, flexShrink: 0,
              background: "var(--accent)",
            }} />
            {f}
          </div>
        ))}
      </div>

      {/* CTA */}
      <button style={{
        marginTop: 24, width: "100%", padding: "12px 0", borderRadius: "var(--r-sm)",
        background: selected
          ? "var(--accent)"
          : dark ? "rgba(255,255,255,0.12)" : "var(--surface-2)",
        color: selected
          ? (dark ? "var(--ink)" : "var(--paper)")
          : dark ? "var(--paper)" : "var(--ink-2)",
        fontWeight: 700, fontSize: 15, border: "none", cursor: "pointer",
        fontFamily: "inherit",
      }}>
        {selected ? "Current plan" : `Switch to ${plan.name}`}
      </button>
    </article>
  );
}

function ConfigScreen() {
  Icon = window.Icon;
  const [selected, setSelected] = React.useState(() => {
    return localStorage.getItem("kairo-plan") || "free";
  });

  const handleSelect = (id) => {
    setSelected(id);
    localStorage.setItem("kairo-plan", id);
  };

  return (
    <div className="screen-enter" style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
      <header>
        <div style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--ink-3)", marginBottom: 12 }}>
          <Icon name="watch" size={18} stroke={1.8} />
          <span className="eyebrow">Configuration</span>
        </div>
        <h1 style={{ fontSize: "clamp(28px, 3.6vw, 38px)", fontWeight: 800, letterSpacing: "-0.025em" }}>
          Choose your plan
        </h1>
        <p style={{ fontSize: 18, color: "var(--ink-2)", marginTop: 12, maxWidth: "52ch" }}>
          Set how often Kairo synthesizes your narrative intelligence.
        </p>
      </header>

      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
        gap: "var(--gap)", marginTop: 4,
        alignItems: "stretch",
      }}>
        {PLANS.map(plan => (
          <PlanCard key={plan.id} plan={plan} selected={selected === plan.id} onSelect={handleSelect} />
        ))}
      </div>

      <article className="card" style={{ padding: "var(--card-pad)", marginTop: 4 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 12 }}>
          <Icon name="spark2" size={16} stroke={1.8} />
          <span className="eyebrow">How refresh frequency works</span>
        </div>
        <p style={{ fontSize: 15.5, color: "var(--ink-2)", lineHeight: 1.65, maxWidth: "60ch" }}>
          Kairo monitors on-chain signals continuously. Your plan determines how often those signals are synthesized
          into updated narratives and briefings. More frequent synthesis means fresher intelligence — especially
          useful in fast-moving market conditions.
        </p>
      </article>
    </div>
  );
}

Object.assign(window, { ConfigScreen });
