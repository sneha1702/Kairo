/* ============================================================
   Kairo — Morning Brief (the 5 cards)
   layout variants: "editorial" | "cards" | "compact"
   ============================================================ */
const { useState } = React;
const K = window.KAIRO;
let Icon, Asset, ForceTag, Dir, Confidence, ExplainToggle, CardLabel;

/* ---------- greeting header ---------- */
function BriefHeader() {
  const u = K.user;
  const { developments, strengthening, risks } = u.summary;
  return (
    <header style={{ marginBottom: 6 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--accent-ink)", marginBottom: 12 }}>
        <Icon name="sun" size={19} stroke={1.8} />
        <span className="eyebrow" style={{ color: "var(--accent-ink)", whiteSpace: "nowrap" }}>{u.date}</span>
      </div>
      <h1 style={{ fontSize: "clamp(30px, 4vw, 40px)", fontWeight: 800, letterSpacing: "-0.025em" }}>
        {u.name === "there" ? "Good morning." : `Good morning, ${u.name}.`}
      </h1>
      <p style={{ fontSize: 18, color: "var(--ink-2)", marginTop: 12, maxWidth: "44ch" }}>
        Here's what moved your market overnight — in about a minute.
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 22 }}>
        <SummaryPill n={developments} label="developments" tone="denim" />
        <SummaryPill n={strengthening} label="trend strengthening" tone="sage" />
        <SummaryPill n={risks} label="major risks" tone="ink" muted={risks === 0} />
        {u.follows && u.follows.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto", color: "var(--ink-3)", fontSize: 13.5 }}>
            <span>Tracked</span>
            <span style={{ display: "flex", gap: 5 }}>
              {u.follows.map(s => <Asset key={s} sym={s} />)}
            </span>
          </div>
        )}
      </div>
    </header>
  );
}

function SummaryPill({ n, label, tone, muted }) {
  const color = muted ? "var(--ink-3)" : tone === "ink" ? "var(--ink)" : `var(--c-${tone}-ink)`;
  return (
    <span style={{
      display: "inline-flex", alignItems: "baseline", gap: 7,
      background: "var(--surface)", border: "1px solid var(--hairline)",
      borderRadius: 99, padding: "8px 15px", boxShadow: "var(--shadow-soft)",
    }}>
      <span className="mono" style={{ fontSize: 17, fontWeight: 700, color }}>{n}</span>
      <span style={{ fontSize: 13.5, color: "var(--ink-2)", fontWeight: 500, whiteSpace: "nowrap" }}>{label}</span>
    </span>
  );
}

/* ---------- Card 1: Today's Market Story ---------- */
function StoryCard({ onOpenNarrative, big }) {
  const s = K.story;
  const [open, setOpen] = useState(false);
  return (
    <article className="card" style={{
      padding: big ? "var(--card-pad)" : "var(--card-pad)",
      background: "linear-gradient(180deg, var(--accent-soft) 0%, var(--surface) 38%)",
      borderColor: "color-mix(in oklch, var(--accent) 22%, var(--hairline))",
    }}>
      <CardLabel icon="spark2">{s.eyebrow}</CardLabel>
      <h2 style={{ fontSize: big ? "clamp(24px, 3vw, 31px)" : 23, fontWeight: 800, letterSpacing: "-0.02em" }}>
        {s.headline}
      </h2>
      <p style={{ fontSize: 16.5, color: "var(--ink-2)", marginTop: 14, lineHeight: 1.6 }}>
        <strong style={{ color: "var(--ink)", fontWeight: 700 }}>Why: </strong>{s.why}
      </p>

      {open && (
        <p style={{ fontSize: 15.5, color: "var(--ink-2)", marginTop: 12, lineHeight: 1.65,
          paddingTop: 14, borderTop: "1px solid var(--hairline)" }}>
          {s.expanded}
        </p>
      )}
      <ExplainToggle open={open} onToggle={() => setOpen(o => !o)} />

      <div style={{ display: "flex", flexWrap: "wrap", gap: "18px 28px", alignItems: "center",
        marginTop: 18, paddingTop: 18, borderTop: "1px solid var(--hairline)" }}>
        {s.assets && s.assets.length > 0 && (
          <Field label="Assets affected">
            <span style={{ display: "flex", gap: 6 }}>{s.assets.map(a => <Asset key={a} sym={a} tone="accent" />)}</span>
          </Field>
        )}
        <Field label="Confidence"><Confidence level={s.confidence} /></Field>
        {s.trend && s.trend.id && s.trend.id !== "pending" && (
          <button onClick={() => onOpenNarrative(s.trend.id)} style={{ marginLeft: "auto", textAlign: "left" }}>
            <Field label="Part of">
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--accent-ink)", fontWeight: 700, fontSize: 14.5 }}>
                {s.trend.label}<Icon name="arrowR" size={15} stroke={2} />
              </span>
            </Field>
          </button>
        )}
      </div>
    </article>
  );
}

function Field({ label, children }) {
  return (
    <div>
      <div className="eyebrow" style={{ marginBottom: 7 }}>{label}</div>
      {children}
    </div>
  );
}

/* ---------- Card 2: Your Holdings ---------- */
function HoldingsCard() {
  const holdings = K.holdings || [];
  return (
    <article className="card" style={{ padding: "var(--card-pad)" }}>
      <CardLabel icon="watch" right={<span style={{ fontSize: 13, color: "var(--ink-3)" }}>Contextual exposure · not prices</span>}>
        What this means for you
      </CardLabel>
      {holdings.length === 0 ? (
        <p style={{ fontSize: 14.5, color: "var(--ink-3)", padding: "8px 0" }}>
          Run detection to see how today's narratives affect your tracked assets.
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column" }}>
          {holdings.map((h, i) => (
            <div key={h.sym} style={{
              display: "flex", alignItems: "center", gap: 14, padding: "13px 0",
              borderTop: i === 0 ? "none" : "1px solid var(--hairline)",
            }}>
              <Dir dir={h.dir} />
              <span className="mono" style={{ fontSize: 15.5, fontWeight: 700, color: "var(--ink)", width: 52 }}>{h.sym}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: h.dir === "up" ? "var(--ink)" : "var(--ink-2)" }}>{h.exposure}</div>
                <div style={{ fontSize: 13.5, color: "var(--ink-3)" }}>{h.note}</div>
              </div>
              {h.force && <span style={{ flexShrink: 0 }}><ForceTag id={h.force} size="sm" /></span>}
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

/* ---------- Card 3: What Changed (events) ---------- */
function EventsCard() {
  return (
    <article className="card" style={{ padding: "var(--card-pad)" }}>
      <CardLabel icon="narr">What changed since yesterday</CardLabel>
      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        {K.events.map((e, i) => (
          <div key={i} style={{
            display: "flex", gap: 14,
            paddingTop: i === 0 ? 0 : 18, borderTop: i === 0 ? "none" : "1px solid var(--hairline)",
          }}>
            <div style={{ flexShrink: 0, paddingTop: 2 }}><ForceTag id={e.force} size="sm" /></div>
            <div style={{ flex: 1 }}>
              <h3 style={{ fontSize: 16.5, fontWeight: 700, lineHeight: 1.35 }}>{e.title}</h3>
              <p style={{ fontSize: 14.5, color: "var(--ink-2)", marginTop: 7 }}>
                <span style={{ color: "var(--ink-3)", fontWeight: 600 }}>Impact — </span>{e.impact}
              </p>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 11 }}>
                {e.assets.map(a => <Asset key={a} sym={a} />)}
                <span style={{ marginLeft: "auto", fontSize: 12.5, color: "var(--ink-4)" }} className="mono">{e.when}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

/* ---------- Card 4: Trend Context ---------- */
function TrendCard() {
  const t = K.trendContext;
  return (
    <article className="card" style={{ padding: "var(--card-pad)" }}>
      <CardLabel icon="history">Trend context</CardLabel>
      <h3 style={{ fontSize: 19, fontWeight: 700 }}>{t.title}</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginTop: 16 }}>
        {t.rows.map(r => (
          <div key={r.label} style={{
            background: "var(--surface-2)", borderRadius: var_r(), padding: "14px 16px",
          }}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>{r.label}</div>
            <div className="mono" style={{ fontSize: 18, fontWeight: 700, color: "var(--pos)" }}>{r.value}</div>
          </div>
        ))}
      </div>
      <p style={{ fontSize: 15.5, color: "var(--ink-2)", marginTop: 16, lineHeight: 1.6,
        paddingLeft: 14, borderLeft: "3px solid var(--accent-soft)" }}>
        {t.interpretation}
      </p>
    </article>
  );
}
function var_r() { return "var(--r-sm)"; }

/* ---------- Card 5: Watch Next ---------- */
function WatchCard() {
  const w = K.watch;
  return (
    <article className="card" style={{ padding: "var(--card-pad)" }}>
      <CardLabel icon="watch">Watch next</CardLabel>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <h3 style={{ fontSize: 19, fontWeight: 700 }}>{w.title}</h3>
          <p style={{ fontSize: 15, color: "var(--ink-2)", marginTop: 8 }}>
            <span style={{ color: "var(--ink-3)", fontWeight: 600 }}>Why — </span>{w.reason}
          </p>
          {w.assets && w.assets.length > 0 && (
            <div style={{ display: "flex", gap: 7, marginTop: 13 }}>{w.assets.map(a => <Asset key={a} sym={a} />)}</div>
          )}
        </div>
        <div style={{ textAlign: "right" }}>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Status</div>
          <StatusBadge status={w.status} />
        </div>
      </div>
      <p style={{ fontSize: 13.5, color: "var(--ink-4)", marginTop: 16, fontStyle: "italic" }}>
        Something to pay attention to — not a recommendation to act.
      </p>
    </article>
  );
}

/* ---------- assembly per layout ---------- */
function MorningBrief({ layout, onOpenNarrative }) {
  ({ Icon, Asset, ForceTag, Dir, Confidence, ExplainToggle, CardLabel, StatusBadge } = window);
  const story = <StoryCard onOpenNarrative={onOpenNarrative} big={layout !== "compact"} />;
  const holdings = <HoldingsCard />;
  const events = <EventsCard />;
  const trend = <TrendCard />;
  const watch = <WatchCard />;

  if (layout === "compact") {
    return (
      <div className="screen-enter" style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
        <BriefHeader />
        {story}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))", gap: "var(--gap)" }}>
          {holdings}{events}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))", gap: "var(--gap)" }}>
          {trend}{watch}
        </div>
      </div>
    );
  }

  // editorial + cards share single-column flow; editorial adds numbered dividers
  return (
    <div className="screen-enter" style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
      <BriefHeader />
      {layout === "editorial"
        ? <>
            {story}
            <Numbered n="01" label="Your holdings">{holdings}</Numbered>
            <Numbered n="02" label="What changed">{events}</Numbered>
            <Numbered n="03" label="Trend context">{trend}</Numbered>
            <Numbered n="04" label="Watch next">{watch}</Numbered>
          </>
        : <>{story}{holdings}{events}{trend}{watch}</>}
    </div>
  );
}

function Numbered({ n, label, children }) {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "8px 2px 12px" }}>
        <span className="mono" style={{ fontSize: 13, fontWeight: 600, color: "var(--accent-ink)" }}>{n}</span>
        <span style={{ flex: 1, height: 1, background: "var(--hairline)" }} />
      </div>
      {children}
    </div>
  );
}

Object.assign(window, { MorningBrief });
