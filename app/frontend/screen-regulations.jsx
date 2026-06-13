/* ============================================================
   Kairo — Policy Pulse screen
   Shows latest crypto regulatory developments from global Tier 1/2 sources.
   ============================================================ */
const { useState, useMemo } = React;

/* ── colour maps ─────────────────────────────────────────── */
const JURISDICTION_COLORS = {
  US: { bg: "var(--c-denim)",  ink: "var(--c-denim-ink)"  },
  EU: { bg: "var(--c-lav)",    ink: "var(--c-lav-ink)"    },
  UK: { bg: "var(--c-teal)",   ink: "var(--c-teal-ink)"   },
  IN: { bg: "var(--c-peach)",  ink: "var(--c-peach-ink)"  },
  CN: { bg: "var(--c-rose)",   ink: "var(--c-rose-ink)"   },
  SG: { bg: "var(--c-sage)",   ink: "var(--c-sage-ink)"   },
  JP: { bg: "var(--c-sage)",   ink: "var(--c-sage-ink)"   },
  AE: { bg: "var(--c-peach)",  ink: "var(--c-peach-ink)"  },
};

const IMPACT_COLORS = {
  restrictive: { bg: "oklch(0.96 0.028 22)",  ink: "oklch(0.52 0.13 22)",  label: "Restrictive"  },
  permissive:  { bg: "oklch(0.95 0.035 150)", ink: "oklch(0.46 0.085 150)", label: "Permissive"  },
  neutral:     { bg: "var(--surface-2)",       ink: "var(--ink-3)",          label: "Neutral"     },
  mixed:       { bg: "oklch(0.95 0.040 75)",  ink: "oklch(0.50 0.080 72)",  label: "Mixed"       },
};

const SIGNIFICANCE_COLORS = {
  high:   { dot: "oklch(0.52 0.13 22)",   label: "High"   },
  medium: { dot: "oklch(0.62 0.090 72)",  label: "Medium" },
  low:    { dot: "var(--ink-4)",           label: "Low"    },
};

const EVENT_LABELS = {
  law_passed:            "Law Passed",
  rule_published:        "Rule Published",
  guidance_issued:       "Guidance Issued",
  enforcement_action:    "Enforcement",
  deadline:              "Deadline",
  consultation_opened:   "Consultation Open",
  consultation_closed:   "Consultation Closed",
};

/* ── sub-components ───────────────────────────────────────── */

function JurisdictionBadge({ code }) {
  if (!code) return null;
  const s = JURISDICTION_COLORS[code] || { bg: "var(--surface-2)", ink: "var(--ink-3)" };
  return (
    <span style={{
      padding: "2px 10px", borderRadius: 6, fontSize: 11.5, fontWeight: 800,
      background: s.bg, color: s.ink, letterSpacing: "0.04em", whiteSpace: "nowrap",
    }}>
      {code}
    </span>
  );
}

function ImpactBadge({ direction }) {
  if (!direction) return null;
  const s = IMPACT_COLORS[direction] || IMPACT_COLORS.neutral;
  return (
    <span style={{
      padding: "2px 9px", borderRadius: 6, fontSize: 11, fontWeight: 700,
      background: s.bg, color: s.ink, whiteSpace: "nowrap",
    }}>
      {s.label}
    </span>
  );
}

function SignificanceDot({ level }) {
  const s = SIGNIFICANCE_COLORS[level] || SIGNIFICANCE_COLORS.low;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      <span style={{
        width: 7, height: 7, borderRadius: "50%",
        background: s.dot, flexShrink: 0,
        boxShadow: level === "high" ? `0 0 0 2px color-mix(in oklch,${s.dot} 30%,transparent)` : "none",
      }} />
      <span style={{ fontSize: 11.5, color: "var(--ink-3)", fontWeight: 600 }}>{s.label}</span>
    </span>
  );
}

function ThemePill({ theme }) {
  return (
    <span style={{
      padding: "2px 8px", borderRadius: 5, fontSize: 10.5, fontWeight: 600,
      background: "var(--surface-2)", color: "var(--ink-3)",
      border: "1px solid var(--hairline)", whiteSpace: "nowrap",
    }}>
      {theme.replace(/_/g, " ")}
    </span>
  );
}

function RegCard({ reg }) {
  const [expanded, setExpanded] = useState(false);
  const clf = reg.classification || {};
  const themes = clf.theme || [];
  const eventLabel = EVENT_LABELS[reg.event_type] || reg.event_type;

  return (
    <div className="card" style={{ padding: "20px 22px", marginBottom: 14 }}>
      {/* ── header row ── */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
        <JurisdictionBadge code={reg.jurisdiction_code} />
        <ImpactBadge direction={clf.impact_direction} />
        <span style={{
          padding: "2px 9px", borderRadius: 6, fontSize: 11, fontWeight: 600,
          background: "var(--surface-2)", color: "var(--ink-3)", border: "1px solid var(--hairline)",
          whiteSpace: "nowrap",
        }}>
          {eventLabel}
        </span>
        <span style={{
          padding: "2px 9px", borderRadius: 6, fontSize: 11, fontWeight: 600,
          background: "var(--surface-2)", color: "var(--ink-4)", marginLeft: "auto",
        }}>
          Tier {reg.source_tier}
        </span>
      </div>

      {/* ── regulation name ── */}
      <div style={{ fontSize: 15.5, fontWeight: 700, color: "var(--ink)", marginBottom: 4, lineHeight: 1.3 }}>
        {reg.regulation_name}
      </div>

      {/* ── regulator + date ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12.5, color: "var(--ink-3)", fontWeight: 600 }}>
          {reg.regulator}
        </span>
        {reg.date_of_event && (
          <span style={{ fontSize: 12, color: "var(--ink-4)" }}>
            {reg.date_of_event}
          </span>
        )}
        <SignificanceDot level={clf.significance} />
      </div>

      {/* ── summary ── */}
      <p style={{ fontSize: 14, color: "var(--ink-2)", lineHeight: 1.6, marginBottom: 12 }}>
        {reg.summary}
      </p>

      {/* ── themes ── */}
      {themes.length > 0 && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
          {themes.map(t => <ThemePill key={t} theme={t} />)}
        </div>
      )}

      {/* ── expand / collapse ── */}
      <button
        onClick={() => setExpanded(x => !x)}
        style={{
          fontSize: 12.5, fontWeight: 600, color: "var(--accent-ink)",
          cursor: "pointer", background: "none", border: "none", padding: 0,
          display: "flex", alignItems: "center", gap: 4,
        }}
      >
        <span style={{
          display: "inline-block",
          transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
          transition: "transform 0.2s",
        }}>▾</span>
        {expanded ? "Less detail" : "More detail"}
      </button>

      {expanded && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--hairline)" }}>
          {/* beneficiary / harm */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
            {clf.beneficiary?.length > 0 && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 5 }}>Beneficiary</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  {clf.beneficiary.map(b => (
                    <span key={b} style={{ fontSize: 12.5, color: "var(--pos)", fontWeight: 600 }}>
                      + {b.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {clf.harm_vector?.filter(h => h !== "none").length > 0 && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 5 }}>Harm vector</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                  {clf.harm_vector.filter(h => h !== "none").map(h => (
                    <span key={h} style={{ fontSize: 12.5, color: "oklch(0.52 0.13 22)", fontWeight: 600 }}>
                      − {h.replace(/_/g, " ")}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* key dates */}
          {reg.key_dates && Object.values(reg.key_dates).some(Boolean) && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>Key dates</div>
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                {Object.entries(reg.key_dates).map(([k, v]) => v ? (
                  <div key={k}>
                    <span style={{ fontSize: 11, color: "var(--ink-4)", textTransform: "capitalize" }}>{k}: </span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-2)", fontFamily: "var(--font-mono)" }}>{v}</span>
                  </div>
                ) : null)}
              </div>
            </div>
          )}

          {/* contradictions */}
          {reg.flagged_contradictions && (
            <div style={{
              background: "oklch(0.97 0.020 75)", border: "1px solid oklch(0.90 0.035 72)",
              borderRadius: 8, padding: "10px 14px", marginBottom: 12,
            }}>
              <span style={{ fontSize: 11.5, fontWeight: 700, color: "oklch(0.50 0.080 72)" }}>⚠ Note: </span>
              <span style={{ fontSize: 12.5, color: "var(--ink-2)" }}>{reg.flagged_contradictions}</span>
            </div>
          )}

          {/* source links */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {reg.source_url && (
              <a
                href={reg.source_url} target="_blank" rel="noopener noreferrer"
                style={{ fontSize: 12.5, fontWeight: 600, color: "var(--accent-ink)", textDecoration: "underline" }}
              >
                Source →
              </a>
            )}
            {reg.official_source_url && reg.official_source_url !== reg.source_url && (
              <a
                href={reg.official_source_url} target="_blank" rel="noopener noreferrer"
                style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink-3)", textDecoration: "underline" }}
              >
                Official doc →
              </a>
            )}
            {!reg.official_source_verified && (
              <span style={{ fontSize: 11.5, color: "var(--ink-4)", alignSelf: "center" }}>
                (official source unverified)
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Main screen ─────────────────────────────────────────── */

function PolicyPulse() {
  const regs = (window.KAIRO?.regulations || []);
  const lastRun = window.KAIRO?.regulation_last_run;

  const [filter, setFilter] = useState("all");
  const [sigFilter, setSigFilter] = useState("all");
  const [search, setSearch] = useState("");

  const jurisdictions = useMemo(() => {
    const codes = [...new Set(regs.map(r => r.jurisdiction_code).filter(Boolean))];
    return codes.sort();
  }, [regs]);

  const filtered = useMemo(() => {
    return regs.filter(r => {
      if (filter !== "all" && r.jurisdiction_code !== filter) return false;
      if (sigFilter !== "all" && r.classification?.significance !== sigFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        if (
          !(r.regulation_name || "").toLowerCase().includes(q) &&
          !(r.summary || "").toLowerCase().includes(q) &&
          !(r.regulator || "").toLowerCase().includes(q) &&
          !(r.jurisdiction || "").toLowerCase().includes(q)
        ) return false;
      }
      return true;
    });
  }, [regs, filter, sigFilter, search]);

  const highCount  = filtered.filter(r => r.classification?.significance === "high").length;
  const restrictCount = filtered.filter(r => r.classification?.impact_direction === "restrictive").length;
  const permissiveCount = filtered.filter(r => r.classification?.impact_direction === "permissive").length;

  const chipStyle = (active) => ({
    padding: "6px 14px", borderRadius: 8, fontSize: 13, fontWeight: 600, cursor: "pointer",
    border: "1px solid " + (active ? "var(--accent)" : "var(--hairline)"),
    background: active ? "var(--accent-soft)" : "var(--surface)",
    color: active ? "var(--accent-ink)" : "var(--ink-3)",
    transition: "all 0.15s",
  });

  if (regs.length === 0) {
    return (
      <div className="screen-enter">
        <div className="eyebrow" style={{ marginBottom: 10 }}>Policy Pulse</div>
        <h1 style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-0.02em", marginBottom: 8 }}>
          Regulatory Intelligence
        </h1>
        <div className="card" style={{ padding: "40px 32px", textAlign: "center", marginTop: 40 }}>
          <div style={{ fontSize: 32, marginBottom: 16 }}>⚖️</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "var(--ink)", marginBottom: 8 }}>
            No regulations loaded yet
          </div>
          <p style={{ fontSize: 14, color: "var(--ink-3)", maxWidth: 360, margin: "0 auto" }}>
            Ask an admin to run "Fetch Regulation Update" in the Admin panel to pull the latest crypto regulatory developments from Tier 1 law firm trackers and official regulator feeds.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="screen-enter">
      {/* ── header ── */}
      <div style={{ marginBottom: 28 }}>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Policy Pulse</div>
        <h1 style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-0.025em", marginBottom: 6 }}>
          Regulatory Intelligence
        </h1>
        <p style={{ fontSize: 14, color: "var(--ink-3)" }}>
          Latest crypto regulatory developments — sourced from Tier 1 law firms &amp; official regulators
          {lastRun?.run_at && (
            <span style={{ marginLeft: 10, color: "var(--ink-4)" }}>
              · last updated {lastRun.run_at.slice(0, 10)}
            </span>
          )}
        </p>
      </div>

      {/* ── stats row ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12, marginBottom: 28 }}>
        {[
          { label: "Total Updates", value: regs.length, color: "var(--ink)" },
          { label: "High Significance", value: highCount, color: "oklch(0.52 0.13 22)" },
          { label: "Restrictive", value: restrictCount, color: "oklch(0.52 0.13 22)" },
          { label: "Permissive", value: permissiveCount, color: "var(--pos)" },
        ].map(s => (
          <div key={s.label} className="card" style={{ padding: "16px 18px" }}>
            <div style={{ fontSize: 24, fontWeight: 800, color: s.color, fontFamily: "var(--font-mono)" }}>{s.value}</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)", fontWeight: 600, marginTop: 2 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* ── filters ── */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 22, alignItems: "center" }}>
        {/* jurisdiction filter */}
        <button style={chipStyle(filter === "all")} onClick={() => setFilter("all")}>All regions</button>
        {jurisdictions.map(jc => (
          <button key={jc} style={chipStyle(filter === jc)} onClick={() => setFilter(jc)}>{jc}</button>
        ))}

        <div style={{ width: 1, height: 24, background: "var(--hairline)", margin: "0 4px" }} />

        {/* significance filter */}
        {["all", "high", "medium", "low"].map(s => (
          <button key={s} style={chipStyle(sigFilter === s)} onClick={() => setSigFilter(s)}>
            {s === "all" ? "All impact" : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}

        {/* search */}
        <input
          type="text"
          placeholder="Search regulations…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{
            marginLeft: "auto", padding: "7px 14px", borderRadius: 8, fontSize: 13.5,
            border: "1px solid var(--hairline-strong)", background: "var(--surface)",
            color: "var(--ink)", outline: "none", minWidth: 200,
            fontFamily: "var(--font-sans)",
          }}
        />
      </div>

      {/* ── results count ── */}
      {filtered.length !== regs.length && (
        <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginBottom: 16, fontWeight: 600 }}>
          Showing {filtered.length} of {regs.length} updates
        </div>
      )}

      {/* ── regulation cards ── */}
      {filtered.length === 0 ? (
        <div className="card" style={{ padding: "32px 24px", textAlign: "center" }}>
          <p style={{ color: "var(--ink-3)", fontSize: 14 }}>No regulations match the current filters.</p>
        </div>
      ) : (
        filtered.map(reg => <RegCard key={reg.id || reg.regulation_name} reg={reg} />)
      )}

      {/* ── footer note ── */}
      <div style={{ marginTop: 32, padding: "18px 22px", background: "var(--surface-2)", borderRadius: 12, border: "1px solid var(--hairline)" }}>
        <div style={{ fontSize: 12, color: "var(--ink-3)", lineHeight: 1.6 }}>
          <strong style={{ color: "var(--ink-2)" }}>Sources:</strong> Tier 1 law firm trackers (Latham &amp; Watkins, Paul Hastings, TRM Labs) · Tier 2 official regulator feeds (SEC, CFTC, ESMA, FCA, RBI, SEBI, MAS) · Tier 3 specialist crypto journalism where verified.
          This is informational only and not legal advice.
        </div>
      </div>
    </div>
  );
}

window.PolicyPulse = PolicyPulse;
