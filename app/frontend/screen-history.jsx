/* ============================================================
   Kairo — Narrative History
   Shows how the top narrative evolved from Day 1 to now,
   with smart time-bucketed episodes (≤3 bullets always).
   ============================================================ */
const K = window.KAIRO;
let Icon, ForceTag, StatusBadge, CardLabel, StrengthCurve;

/* ---- age label helper ---- */
function _ageLabel(days) {
  if (days === 1) return "Day 1";
  if (days <= 7)  return `${days} days`;
  if (days <= 28) return `${Math.floor(days / 7)} week${Math.floor(days / 7) > 1 ? "s" : ""}`;
  return `${Math.floor(days / 30)} month${Math.floor(days / 30) > 1 ? "s" : ""}`;
}

/* ---- single journey step in the evolution timeline ---- */
function JourneyStep({ ep, last }) {
  const f = (K.forces && K.forces[ep.force]) || { color: "sage" };
  // Period labels (summarised buckets) get a pill style instead of "Day X · Date"
  const isPeriod = /ago|week|month/i.test(ep.date || "");

  return (
    <div style={{ display: "flex", gap: 20, position: "relative" }}>
      {/* connector */}
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
        <span style={{
          width: 14, height: 14, borderRadius: 99,
          background: `var(--c-${f.color}-ink)`,
          boxShadow: `0 0 0 4px var(--c-${f.color})`,
          marginTop: 5, zIndex: 1,
        }} />
        {!last && <span style={{ flex: 1, width: 2, background: "var(--hairline)", marginTop: 6 }} />}
      </div>

      {/* content */}
      <div style={{ paddingBottom: last ? 0 : 36, flex: 1 }}>
        {/* time label row */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 9, flexWrap: "wrap" }}>
          {isPeriod ? (
            <span style={{
              fontSize: 12, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase",
              color: "var(--accent-ink)", background: "var(--accent-soft)",
              borderRadius: 99, padding: "3px 10px",
            }}>{ep.date}</span>
          ) : (
            <span className="mono" style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-3)" }}>
              Day {ep.day} · {ep.date}
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

/* ---- main screen ---- */
function NarrativeHistory() {
  ({ Icon, ForceTag, StatusBadge, CardLabel, StrengthCurve } = window);

  const t = K.tracker;
  const hasData = t && t.title && t.title !== "No narrative detected" && (t.day || 0) > 0;

  if (!hasData) {
    return (
      <div className="screen-enter" style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>
        <header>
          <div style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--ink-3)", marginBottom: 12 }}>
            <Icon name="history" size={18} stroke={1.8} />
            <span className="eyebrow">Narrative evolution</span>
          </div>
          <h1 style={{ fontSize: "clamp(26px, 3.2vw, 34px)", fontWeight: 800, letterSpacing: "-0.025em" }}>
            No narrative tracked yet
          </h1>
          <p style={{ fontSize: 16, color: "var(--ink-2)", marginTop: 12, lineHeight: 1.6 }}>
            Run detection to start tracking a narrative. Once active, you'll see its full evolution here — what happened day by day, how the signal strengthened, and what it means.
          </p>
        </header>
      </div>
    );
  }

  const episodes  = t.episodes || [];
  const hasCurve  = t.curve && t.curve.length > 1;
  const hasConclusion = t.why_matters || t.implications;
  const ageLabel  = _ageLabel(t.day || 1);

  return (
    <div className="screen-enter" style={{ display: "flex", flexDirection: "column", gap: "var(--gap)" }}>

      {/* ── Header ───────────────────────────────────────────────── */}
      <header>
        <div style={{ display: "flex", alignItems: "center", gap: 9, color: "var(--ink-3)", marginBottom: 12 }}>
          <Icon name="history" size={18} stroke={1.8} />
          <span className="eyebrow">Narrative evolution</span>
        </div>
        <h1 style={{ fontSize: "clamp(22px, 3vw, 32px)", fontWeight: 800,
          letterSpacing: "-0.025em", lineHeight: 1.2 }}>{t.title}</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12, flexWrap: "wrap" }}>
          <StatusBadge status={t.status} />
          <span style={{ fontSize: 14, color: "var(--ink-3)", fontWeight: 600 }}>
            Active for {ageLabel}
          </span>
          <span className="mono" style={{ fontSize: 14, fontWeight: 700, color: "var(--ink-2)" }}>
            Strength {(t.strength || 0).toFixed(1)} / 10
          </span>
        </div>
      </header>

      {/* ── How it developed (bucketed timeline) ─────────────────── */}
      {episodes.length > 0 && (
        <article className="card" style={{ padding: "calc(var(--card-pad) + 4px)" }}>
          <CardLabel icon="narr">How this narrative developed</CardLabel>
          <p style={{ fontSize: 13.5, color: "var(--ink-3)", marginTop: -6, marginBottom: 22, lineHeight: 1.6 }}>
            {t.day <= 7
              ? "Each day this narrative has been active, from when it first appeared to now."
              : t.day <= 28
              ? "Older days are grouped into weekly summaries — recent activity shown individually."
              : "Older weeks are rolled into a single summary. The most recent activity is shown individually."
            }
          </p>
          {episodes.map((ep, i, arr) => (
            <JourneyStep key={i} ep={ep} last={i === arr.length - 1} />
          ))}
        </article>
      )}

      {/* ── Strength arc ─────────────────────────────────────────── */}
      {hasCurve && (
        <article className="card" style={{ padding: "calc(var(--card-pad) + 4px)" }}>
          <CardLabel
            icon="history"
            right={<span style={{ fontSize: 13, color: "var(--ink-3)" }}>{t.curve.length}-day arc</span>}
          >
            Signal strength over time
          </CardLabel>
          <div style={{ background: "var(--surface-2)", borderRadius: "var(--r-md)",
            padding: "20px 18px 8px", marginTop: 4 }}>
            <StrengthCurve data={t.curve} />
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-4)" }}>Day 1</span>
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-4)" }}>
                Today · {(t.strength || 0).toFixed(1)} / 10
              </span>
            </div>
          </div>
        </article>
      )}

      {/* ── Where it stands ──────────────────────────────────────── */}
      {hasConclusion && (
        <article className="card" style={{
          padding: "calc(var(--card-pad) + 2px)",
          background: "var(--ink)", borderColor: "var(--ink)", color: "var(--paper)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 14, opacity: 0.7 }}>
            <Icon name="spark2" size={16} stroke={1.8} />
            <span className="eyebrow" style={{ color: "var(--paper)", opacity: 0.8 }}>
              Where this narrative stands
            </span>
          </div>
          <p style={{ fontSize: "clamp(15px, 1.9vw, 19px)", lineHeight: 1.65, fontWeight: 600,
            color: "var(--paper)", maxWidth: "48ch", textWrap: "balance" }}>
            {t.why_matters || t.implications}
          </p>
          {t.watch_for && (
            <div style={{ marginTop: 18, paddingTop: 16,
              borderTop: "1px solid rgba(255,255,255,0.14)" }}>
              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em",
                textTransform: "uppercase", color: "rgba(255,255,255,0.45)", marginBottom: 6 }}>
                Watch for
              </div>
              <p style={{ fontSize: 14.5, color: "rgba(255,255,255,0.72)",
                lineHeight: 1.6, fontStyle: "italic", margin: 0 }}>{t.watch_for}</p>
            </div>
          )}
          {t.risk_note && (
            <div style={{ marginTop: 14, paddingTop: 14,
              borderTop: "1px solid rgba(255,255,255,0.10)" }}>
              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em",
                textTransform: "uppercase", color: "rgba(255,255,255,0.38)", marginBottom: 5 }}>
                Risk
              </div>
              <p style={{ fontSize: 14, color: "rgba(255,255,255,0.58)",
                lineHeight: 1.6, margin: 0 }}>{t.risk_note}</p>
            </div>
          )}
        </article>
      )}

    </div>
  );
}

Object.assign(window, { NarrativeHistory });
