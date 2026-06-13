/* ============================================================
   Kairo — Narrative History
   Two sections:
     1. Retired narratives — died or low-strength for 2+ weeks, shown
        as a timeline with the date each moved to history.
     2. Pattern Memory — how the top narrative compares with prior cycles.
   ============================================================ */
const K = window.KAIRO;
let Icon, ForceTag, Asset, StatusBadge, CardLabel, StrengthCurve,
    PhaseChip, SmartIntentBadge;

/* ---- age label helper ---- */
function _ageLabel(days, granularity) {
  if (granularity === 'week') {
    const w = days;
    if (w <= 1)  return "1 week";
    if (w <= 4)  return `${w} weeks`;
    return `${Math.floor(w / 4)} month${Math.floor(w / 4) > 1 ? "s" : ""}`;
  }
  if (days === 1) return "Day 1";
  if (days <= 7)  return `${days} days`;
  if (days <= 28) return `${Math.floor(days / 7)} week${Math.floor(days / 7) > 1 ? "s" : ""}`;
  return `${Math.floor(days / 30)} month${Math.floor(days / 30) > 1 ? "s" : ""}`;
}

/* ---- single journey step (active narrative evolution) ---- */
function JourneyStep({ ep, last }) {
  const f = (K.forces && K.forces[ep.force]) || { color: "sage" };
  const isPeriod = /ago|week|month/i.test(ep.date || "");

  return (
    <div style={{ display: "flex", gap: 20, position: "relative" }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
        <span style={{
          width: 14, height: 14, borderRadius: 99,
          background: `var(--c-${f.color}-ink)`,
          boxShadow: `0 0 0 4px var(--c-${f.color})`,
          marginTop: 5, zIndex: 1,
        }} />
        {!last && <span style={{ flex: 1, width: 2, background: "var(--hairline)", marginTop: 6 }} />}
      </div>

      <div style={{ paddingBottom: last ? 0 : 36, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 9, flexWrap: "wrap" }}>
          {isPeriod ? (
            <span style={{
              fontSize: 12, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase",
              color: "var(--accent-ink)", background: "var(--accent-soft)",
              borderRadius: 99, padding: "3px 10px",
            }}>{ep.date}</span>
          ) : (
            <span className="mono" style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-3)" }}>
              {ep.granularity === 'week' ? 'Week' : 'Day'} {ep.day} · {ep.date}
            </span>
          )}
          <ForceTag id={ep.force} size="sm" />
        </div>

        <h3 style={{ fontSize: 17, fontWeight: 700, lineHeight: 1.3, marginBottom: 8 }}>{ep.headline}</h3>

        {ep.detail && ep.detail !== ep.headline && (
          <p style={{ fontSize: 13.5, color: "var(--ink-3)", marginBottom: 8,
            lineHeight: 1.55, fontStyle: "italic" }}>{ep.detail}</p>
        )}

        <p style={{ fontSize: 15, color: "var(--ink-2)", lineHeight: 1.7 }}>{ep.body}</p>
      </div>
    </div>
  );
}

/* ---- archived narrative timeline entry ---- */
function ArchivedEntry({ n, last }) {
  return (
    <div style={{ display: "flex", gap: 0, position: "relative" }}>

      {/* ── Timeline track ── */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0, width: 28 }}>
        <span style={{
          width: 13, height: 13, borderRadius: 99,
          background: "var(--ink-4)",
          boxShadow: "0 0 0 4px var(--surface-2)",
          marginTop: 22, zIndex: 1, flexShrink: 0,
        }} />
        {!last && <span style={{ flex: 1, width: 2, background: "var(--hairline)", marginTop: 6 }} />}
      </div>

      {/* ── Content ── */}
      <div style={{ flex: 1, paddingBottom: last ? 0 : 36, paddingLeft: 16 }}>

        {/* Date + reason stamp */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
          <span className="mono" style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink-4)" }}>
            {n.archived_at || "—"}
          </span>
          <span style={{
            fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
            background: "var(--surface-2)", color: "var(--ink-4)",
            borderRadius: 99, padding: "2px 9px",
            border: "1px solid var(--hairline-strong)",
          }}>
            {n.archived_reason}
          </span>
        </div>

        {/* Narrative tile — same layout as the Narratives tab */}
        <div className="card" style={{ padding: "20px 24px", opacity: 0.82 }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 20 }}>

            {/* Left: meta + title + summary + assets */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
                <span className="mono" style={{ fontSize: 11.5, color: "var(--ink-4)", fontWeight: 600 }}>
                  {n.granularity === "week" ? "Week" : "Day"} {n.day}
                </span>
                <ForceTag id={n.force} size="sm" />
                {n.phase && <PhaseChip phase={n.phase} />}
                {n.smart_money_intent && <SmartIntentBadge intent={n.smart_money_intent} />}
              </div>

              <h3 style={{ fontSize: 18, fontWeight: 800, lineHeight: 1.25, marginBottom: 8,
                letterSpacing: "-0.015em", color: "var(--ink-2)" }}>
                {n.title}
              </h3>

              {n.summary_line && (
                <p style={{ fontSize: 14, color: "var(--ink-3)", lineHeight: 1.6, margin: "0 0 10px" }}>
                  {n.summary_line}
                </p>
              )}

              {n.assets && n.assets.length > 0 && (
                <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                  {n.assets.map(a => <Asset key={a} sym={a} />)}
                </div>
              )}
            </div>

            {/* Right: strength + status */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end",
              gap: 12, flexShrink: 0, minWidth: 90 }}>
              <div style={{ textAlign: "right" }}>
                <div className="mono" style={{ fontSize: 24, fontWeight: 800, color: "var(--ink-4)", lineHeight: 1 }}>
                  {n.strength.toFixed(1)}
                </div>
                <div className="eyebrow" style={{ marginTop: 3 }}>final strength</div>
              </div>
              <StatusBadge status={n.status} size="sm" />
            </div>

          </div>
        </div>

      </div>
    </div>
  );
}

/* ---- archived narratives section ---- */
function ArchivedNarrativesSection() {
  const archived = K.archived_narratives || [];
  if (archived.length === 0) return null;

  return (
    <article className="card" style={{ padding: "calc(var(--card-pad) + 4px)" }}>
      <CardLabel
        icon="history"
        right={
          <span style={{ color: "var(--ink-4)", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600 }}>
            {archived.length} retired
          </span>
        }
      >
        Narratives that faded
      </CardLabel>
      <p style={{ fontSize: 13.5, color: "var(--ink-3)", marginTop: -6, marginBottom: 24, lineHeight: 1.6 }}>
        Narratives that died, reversed, or stayed low-strength for more than two weeks.
        Each point on the timeline marks the date it moved here.
      </p>

      {/* Timeline */}
      <div style={{ paddingLeft: 0 }}>
        {archived.map((n, i, arr) => (
          <ArchivedEntry key={n.id + i} n={n} last={i === arr.length - 1} />
        ))}
      </div>
    </article>
  );
}

/* ---- main screen ---- */
function NarrativeHistory() {
  ({ Icon, ForceTag, Asset, StatusBadge, CardLabel, StrengthCurve,
     PhaseChip, SmartIntentBadge } = window);

  const hasArchived = (K.archived_narratives || []).length > 0;

  if (!hasArchived) {
    return (
      <div className="screen-enter" style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
        <header>
          <div style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--ink-3)", marginBottom: 12 }}>
            <Icon name="history" size={18} stroke={1.8} />
            <span className="eyebrow">Narrative history</span>
          </div>
          <h1 style={{ fontSize: "clamp(26px, 3.2vw, 34px)", fontWeight: 800, letterSpacing: "-0.025em" }}>
            Nothing here yet
          </h1>
          <p style={{ fontSize: 16, color: "var(--ink-2)", marginTop: 12, lineHeight: 1.6 }}>
            Narratives that die out, reverse, or stay low-strength for more than two weeks will appear here with a timeline of when they faded.
          </p>
        </header>
      </div>
    );
  }

  return (
    <div className="screen-enter" style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
      <ArchivedNarrativesSection />
    </div>
  );
}

Object.assign(window, { NarrativeHistory });
