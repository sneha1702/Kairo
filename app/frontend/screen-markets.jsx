/* ============================================================
   Kairo — Markets screen
   Beginner-friendly cards with progressive disclosure.
   Cards show core info at a glance; expanded view reveals
   performance history, TradFi analogy, activity summary, and links.
   ============================================================ */
const { useState, useMemo } = React;

/* ──────────────────────────────────────────────────────────
   Sub-components
   ────────────────────────────────────────────────────────── */

const ECO_COLORS = {
  L1:         { bg: "var(--c-sage)",   ink: "var(--c-sage-ink)"   },
  L2:         { bg: "var(--c-denim)",  ink: "var(--c-denim-ink)"  },
  Sidechain:  { bg: "var(--c-teal)",   ink: "var(--c-teal-ink)"   },
  DeFi:       { bg: "var(--c-peach)",  ink: "var(--c-peach-ink)"  },
  Stablecoin: { bg: "var(--c-lav)",    ink: "var(--c-lav-ink)"    },
  Oracle:     { bg: "var(--c-rose)",   ink: "var(--c-rose-ink)"   },
  Exchange:   { bg: "var(--c-teal)",   ink: "var(--c-teal-ink)"   },
  Payments:   { bg: "var(--c-lav)",    ink: "var(--c-lav-ink)"    },
  Privacy:    { bg: "var(--surface-2)","ink": "var(--ink-3)"       },
  Interop:    { bg: "var(--c-sage)",   ink: "var(--c-sage-ink)"   },
};

function EcoBadge({ category }) {
  if (!category) return null;
  const s = ECO_COLORS[category] || { bg: "var(--surface-2)", ink: "var(--ink-3)" };
  return (
    <span style={{
      padding: "2px 9px", borderRadius: 6, fontSize: 11.5, fontWeight: 700,
      background: s.bg, color: s.ink, letterSpacing: "0.02em", whiteSpace: "nowrap",
    }}>
      {category}
    </span>
  );
}

function PerfPill({ value, label }) {
  const num = parseFloat(value);
  if (value === null || value === undefined || isNaN(num)) {
    return (
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 11, color: "var(--ink-4)", marginBottom: 4, whiteSpace: "nowrap" }}>{label}</div>
        <span className="mono" style={{ fontSize: 13.5, color: "var(--ink-4)" }}>—</span>
      </div>
    );
  }
  const pos = num >= 0;
  const color = pos ? "var(--pos)" : "oklch(0.52 0.13 22)";
  const bg    = pos ? "oklch(0.95 0.035 150)" : "oklch(0.96 0.028 22)";
  return (
    <div style={{ textAlign: "center" }}>
      <div style={{ fontSize: 11, color: "var(--ink-4)", marginBottom: 4, whiteSpace: "nowrap" }}>{label}</div>
      <div style={{
        display: "inline-flex", alignItems: "center", gap: 3,
        padding: "3px 10px", borderRadius: 8, background: bg,
      }}>
        <span style={{ fontSize: 10, color }}>{pos ? "▲" : "▼"}</span>
        <span className="mono" style={{ fontWeight: 700, fontSize: 14, color }}>
          {Math.abs(num).toFixed(2)}%
        </span>
      </div>
    </div>
  );
}

/* compact inline perf — used in card header */
function PerfInline({ value }) {
  const num = parseFloat(value);
  if (value === null || value === undefined || isNaN(num)) return null;
  const pos   = num >= 0;
  const color = pos ? "var(--pos)" : "oklch(0.52 0.13 22)";
  const bg    = pos ? "oklch(0.95 0.035 150)" : "oklch(0.96 0.028 22)";
  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: 3,
      padding: "3px 9px", borderRadius: 7, background: bg,
    }}>
      <span style={{ fontSize: 10, color }}>{pos ? "▲" : "▼"}</span>
      <span className="mono" style={{ fontWeight: 700, fontSize: 13, color }}>
        {Math.abs(num).toFixed(2)}%
      </span>
      <span style={{ fontSize: 11, color, marginLeft: 1, fontWeight: 500 }}>today</span>
    </div>
  );
}

function CryptoLogo({ symbol, logoUrl, size = 38 }) {
  const [err, setErr] = useState(false);
  const COLORS = ["#E8967A","#7B9FE0","#7BC4AA","#C4A97B","#9B7BC4","#7BC4C4","#C47B9B","#B4C47B"];
  const bg = COLORS[((symbol || "").charCodeAt(0) || 0) % COLORS.length];
  if (logoUrl && !err) {
    return (
      <img src={logoUrl} alt={symbol} width={size} height={size}
        style={{ borderRadius: "50%", display: "block", flexShrink: 0 }}
        onError={() => setErr(true)} />
    );
  }
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%", background: bg,
      display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
    }}>
      <span style={{ color: "#fff", fontWeight: 700, fontSize: Math.round(size * 0.38), fontFamily: "var(--font-mono)" }}>
        {(symbol || "?").slice(0, 2)}
      </span>
    </div>
  );
}

function formatPrice(val) {
  const n = parseFloat(val);
  if (!n && n !== 0) return "—";
  if (n >= 1000) return "$" + n.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (n >= 1)    return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n >= 0.01) return "$" + n.toFixed(4);
  return "$" + n.toFixed(6);
}

function formatMcap(val) {
  const n = parseFloat(val);
  if (!n) return "—";
  if (n >= 1e12) return "$" + (n/1e12).toFixed(2) + " trillion";
  if (n >= 1e9)  return "$" + (n/1e9).toFixed(1)  + " billion";
  if (n >= 1e6)  return "$" + (n/1e6).toFixed(0)  + " million";
  return "$" + n.toLocaleString();
}

function mcapHint(val) {
  const n = parseFloat(val);
  if (n >= 500e9)  return "one of the largest crypto projects";
  if (n >= 100e9)  return "very large project";
  if (n >= 10e9)   return "large project";
  if (n >= 1e9)    return "mid-size project";
  return "smaller project";
}

/* separator line used inside expanded sections */
function Sep() {
  return <div style={{ height: 1, background: "var(--hairline)", margin: "0 22px" }} />;
}

/* ──────────────────────────────────────────────────────────
   Individual project card
   ────────────────────────────────────────────────────────── */

function MarketCard({ project }) {
  const [open, setOpen] = useState(false);

  const hasAnalysis  = !!(project.description || project.ecosystem_category);
  const hasTradFi    = !!(project.trad_fi_equivalent);
  // activity: prefer new fields, fall back to legacy roadmap fields
  const hasActivity  = !!(project.activity_summary || project.roadmap_summary);
  const activityText = project.activity_summary || project.roadmap_summary;
  const activityUrl  = project.activity_source_url || project.roadmap_source_url;
  const activityDate = project.activity_source_date || project.roadmap_source_date;
  // display name: use Gemini's common name (e.g. "Binance Coin") if available, else CMC name
  const displayName  = project.display_name || project.name;

  return (
    <article
      className="card"
      style={{ marginBottom: 10, overflow: "hidden", transition: "box-shadow 0.15s" }}
      onMouseEnter={e => e.currentTarget.style.boxShadow = "0 2px 8px oklch(0.5 0.02 60 / 0.10), 0 8px 28px oklch(0.5 0.02 60 / 0.09)"}
      onMouseLeave={e => e.currentTarget.style.boxShadow = "var(--shadow-card)"}
    >
      {/* ── Always-visible header ── */}
      <div style={{ padding: "18px 22px 14px" }}>
        <div style={{ display: "flex", gap: 13, alignItems: "flex-start" }}>

          {/* Rank badge */}
          <div style={{
            minWidth: 30, height: 30, display: "flex", alignItems: "center", justifyContent: "center",
            borderRadius: 8, background: "var(--surface-2)", flexShrink: 0, marginTop: 4,
          }}>
            <span className="mono" style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-4)" }}>
              {project.rank}
            </span>
          </div>

          {/* Logo */}
          <CryptoLogo symbol={project.symbol} logoUrl={project.logo_url} size={40} />

          {/* Name, badges, description */}
          <div style={{ flex: 1, minWidth: 0 }}>
            {/* Project name as prominent heading */}
            <h3 style={{ margin: "0 0 4px", fontWeight: 800, fontSize: 18, color: "var(--ink)", letterSpacing: "-0.015em", lineHeight: 1.2 }}>
              {displayName}
            </h3>
            {/* Ticker + ecosystem category on one row */}
            <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap", marginBottom: 6 }}>
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-4)", fontWeight: 600 }}>
                {project.symbol}
              </span>
              {project.ecosystem_category && <EcoBadge category={project.ecosystem_category} />}
            </div>
            {/* Market share chip — shown when CMC data has been refreshed */}
            {project.market_share_pct != null && project.market_share_pct > 0 && (
              <div style={{ marginBottom: 6 }}>
                <span style={{
                  display: "inline-flex", alignItems: "center", gap: 4,
                  fontSize: 11.5, fontWeight: 700, padding: "3px 9px", borderRadius: 7,
                  background: "var(--c-denim)", color: "var(--c-denim-ink)", whiteSpace: "nowrap",
                }}>
                  📈 {parseFloat(project.market_share_pct).toFixed(2)}% of total crypto market
                </span>
              </div>
            )}
            <p style={{ margin: 0, fontSize: 14, color: "var(--ink-3)", lineHeight: 1.5 }}>
              {project.description || (
                <span style={{ fontStyle: "italic", color: "var(--ink-4)" }}>
                  Run <strong style={{ fontStyle: "normal" }}>AI Market Analysis</strong> in Admin to get a plain-English summary.
                </span>
              )}
            </p>
          </div>

          {/* Price + today's perf */}
          <div style={{ flexShrink: 0, textAlign: "right" }}>
            <div className="mono" style={{ fontWeight: 800, fontSize: 19, color: "var(--ink)", letterSpacing: "-0.02em", marginBottom: 5 }}>
              {formatPrice(project.price_usd)}
            </div>
            <PerfInline value={project.perf_1d} />
          </div>
        </div>

        {/* Toggle */}
        <div style={{ marginTop: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          {/* quick peek at what's inside when collapsed */}
          {!open && (hasAnalysis || hasTradFi || hasActivity) && (
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {hasTradFi && (
                <span style={{ fontSize: 11.5, color: "var(--ink-4)", display: "flex", alignItems: "center", gap: 3 }}>
                  💡 Like {project.trad_fi_equivalent}
                </span>
              )}
              {hasActivity && (
                <span style={{ fontSize: 11.5, color: "var(--ink-4)", display: "flex", alignItems: "center", gap: 3 }}>
                  📡 Activity summary inside
                </span>
              )}
            </div>
          )}
          {!open && !hasAnalysis && <span />}

          <button
            onClick={() => setOpen(v => !v)}
            style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              padding: "5px 13px", borderRadius: 8, cursor: "pointer",
              border: "1px solid var(--hairline)",
              background: open ? "var(--accent-soft)" : "var(--surface-2)",
              color:  open ? "var(--accent-ink)"  : "var(--ink-3)",
              fontSize: 12.5, fontWeight: 600, transition: "background 0.14s, color 0.14s",
              marginLeft: "auto",
            }}
          >
            {open ? "▲ Less" : "▼ More details"}
          </button>
        </div>
      </div>

      {/* ── Expanded details ── */}
      {open && (
        <div>
          <Sep />

          {/* Performance section */}
          <div style={{ padding: "16px 22px" }}>
            <div className="eyebrow" style={{ marginBottom: 14 }}>Performance over time</div>
            <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
              <PerfPill value={project.perf_1d}  label="Past 24 hours" />
              <PerfPill value={project.perf_7d}  label="Past 7 days"   />
              <PerfPill value={project.perf_30d} label="Past 30 days"  />
            </div>
            <p style={{ margin: "10px 0 0", fontSize: 12.5, color: "var(--ink-4)", lineHeight: 1.5 }}>
              These numbers show how the price changed compared to the same point in time before.
              A positive % means the price went up; negative means it went down.
            </p>
          </div>

          <Sep />

          {/* Market size */}
          <div style={{ padding: "14px 22px", display: "flex", alignItems: "flex-start", gap: 12 }}>
            <span style={{ fontSize: 22, lineHeight: 1 }}>📊</span>
            <div>
              <div className="eyebrow" style={{ marginBottom: 5 }}>Total market size</div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                <div style={{ fontWeight: 700, fontSize: 16, color: "var(--ink)" }}>
                  {formatMcap(project.market_cap)}
                </div>
                {project.market_share_pct != null && (
                  <span style={{ fontSize: 13, color: "var(--ink-3)", fontWeight: 600 }}>
                    — {parseFloat(project.market_share_pct).toFixed(2)}% of all crypto
                  </span>
                )}
              </div>
              <div style={{ fontSize: 13, color: "var(--ink-3)", marginTop: 3 }}>
                {mcapHint(project.market_cap)} — this is the total value of all coins/tokens in circulation
              </div>
            </div>
          </div>

          {/* Ecosystem description */}
          {project.ecosystem_description && (
            <>
              <Sep />
              <div style={{ padding: "14px 22px", display: "flex", alignItems: "flex-start", gap: 12 }}>
                <span style={{ fontSize: 22, lineHeight: 1 }}>🌐</span>
                <div>
                  <div className="eyebrow" style={{ marginBottom: 5 }}>Where it fits in crypto</div>
                  <EcoBadge category={project.ecosystem_category} />
                  <p style={{ margin: "8px 0 0", fontSize: 14, color: "var(--ink-2)", lineHeight: 1.6 }}>
                    {project.ecosystem_description}
                  </p>
                </div>
              </div>
            </>
          )}

          <Sep />

          {/* TradFi equivalent */}
          {hasTradFi ? (
            <div style={{ padding: "14px 22px", display: "flex", alignItems: "flex-start", gap: 12 }}>
              <span style={{ fontSize: 22, lineHeight: 1 }}>💡</span>
              <div>
                <div className="eyebrow" style={{ marginBottom: 5 }}>In traditional finance, this is like…</div>
                <div style={{
                  display: "inline-block", padding: "5px 14px", borderRadius: 9,
                  background: "var(--accent-soft)", color: "var(--accent-ink)",
                  fontWeight: 700, fontSize: 15, marginBottom: 8,
                }}>
                  {project.trad_fi_equivalent}
                </div>
                <p style={{ margin: 0, fontSize: 14, color: "var(--ink-2)", lineHeight: 1.6 }}>
                  {project.trad_fi_explanation}
                </p>
              </div>
            </div>
          ) : (
            <div style={{ padding: "14px 22px", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 18 }}>💡</span>
              <span style={{ fontSize: 13, color: "var(--ink-4)", fontStyle: "italic" }}>
                Traditional finance comparison not generated yet — run <strong style={{ fontStyle: "normal" }}>AI Market Analysis</strong> in Admin.
              </span>
            </div>
          )}

          <Sep />

          {/* Activity section — news, releases, and roadmap combined */}
          {hasActivity ? (
            <div style={{ padding: "14px 22px", display: "flex", alignItems: "flex-start", gap: 12 }}>
              <span style={{ fontSize: 22, lineHeight: 1 }}>📡</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="eyebrow" style={{ marginBottom: 8 }}>What they're actually doing</div>

                {/* Latest release chip */}
                {project.latest_release && (
                  <div style={{ marginBottom: 8 }}>
                    <span style={{
                      display: "inline-flex", alignItems: "center", gap: 5,
                      fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 7,
                      background: "var(--c-teal)", color: "var(--c-teal-ink)",
                    }}>
                      🚀 Latest release: {project.latest_release}
                    </span>
                  </div>
                )}

                {/* Latest news headline */}
                {project.latest_news_headline && (
                  <p style={{ margin: "0 0 8px", fontSize: 14, color: "var(--ink-2)", lineHeight: 1.55, fontWeight: 600 }}>
                    {project.latest_news_headline}
                  </p>
                )}

                {/* Activity summary */}
                <p style={{ margin: "0 0 10px", fontSize: 14.5, color: "var(--ink-2)", lineHeight: 1.7 }}>
                  {activityText}
                </p>

                {/* Source row */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  {activityDate && (
                    <span style={{ fontSize: 12, color: "var(--ink-4)" }}>
                      Info as of {activityDate}
                    </span>
                  )}
                  {activityUrl && (
                    <>
                      <span style={{ color: "var(--hairline-strong)" }}>·</span>
                      <a href={activityUrl} target="_blank" rel="noopener noreferrer"
                        style={{ fontSize: 12, color: "var(--accent-ink)", textDecoration: "underline" }}>
                        view source
                      </a>
                    </>
                  )}
                  {project.analysis_confidence && (
                    <>
                      <span style={{ color: "var(--hairline-strong)" }}>·</span>
                      <span style={{ fontSize: 11.5, color: "var(--ink-4)" }}>
                        AI confidence: {project.analysis_confidence}
                      </span>
                    </>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div style={{ padding: "14px 22px", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 18 }}>📡</span>
              <span style={{ fontSize: 13, color: "var(--ink-4)", fontStyle: "italic" }}>
                Latest activity not generated yet — run <strong style={{ fontStyle: "normal" }}>AI Market Analysis</strong> in Admin.
              </span>
            </div>
          )}

          <Sep />

          {/* Links row */}
          <div style={{ padding: "14px 22px", display: "flex", gap: 10, flexWrap: "wrap" }}>
            {project.website && (
              <LinkButton href={project.website} label="🌐 Official Website" />
            )}
            {(activityUrl || project.roadmap_url) &&
              (activityUrl || project.roadmap_url) !== project.website && (
              <LinkButton href={activityUrl || project.roadmap_url} label="📡 Activity Page" accent />
            )}
          </div>
        </div>
      )}
    </article>
  );
}

function LinkButton({ href, label, accent }) {
  const [hov, setHov] = useState(false);
  return (
    <a
      href={href} target="_blank" rel="noopener noreferrer"
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        padding: "7px 15px", borderRadius: 9, fontSize: 13.5, fontWeight: 600,
        textDecoration: "none", transition: "background 0.13s",
        border: "1px solid var(--hairline)",
        background: hov
          ? (accent ? "var(--accent-soft)" : "var(--surface)")
          : (accent ? "oklch(0.97 0.016 50)" : "var(--surface-2)"),
        color: accent ? "var(--accent-ink)" : "var(--ink-2)",
      }}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
    >
      {label}
    </a>
  );
}

/* ──────────────────────────────────────────────────────────
   Toolbar
   ────────────────────────────────────────────────────────── */

const SORT_OPTS = [
  { key: "rank",     label: "By size"    },
  { key: "perf_1d",  label: "Best today" },
  { key: "perf_7d",  label: "Best week"  },
  { key: "perf_30d", label: "Best month" },
];

function Toolbar({ sort, setSort, search, setSearch }) {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 20 }}>
      {/* Sort pill group */}
      <div style={{
        display: "flex", gap: 3, background: "var(--surface-2)",
        padding: 3, borderRadius: 11, border: "1px solid var(--hairline)",
      }}>
        {SORT_OPTS.map(o => (
          <button key={o.key} onClick={() => setSort(o.key)} style={{
            padding: "5px 13px", borderRadius: 9, fontSize: 13, fontWeight: 600, cursor: "pointer",
            background: sort === o.key ? "var(--surface)" : "transparent",
            color:      sort === o.key ? "var(--ink)"    : "var(--ink-3)",
            boxShadow:  sort === o.key ? "var(--shadow-soft)" : "none",
            border:     sort === o.key ? "1px solid var(--hairline)" : "1px solid transparent",
            transition: "all 0.12s",
          }}>{o.label}</button>
        ))}
      </div>

      {/* Search */}
      <div style={{ position: "relative", flex: "1 1 200px", maxWidth: 280 }}>
        <span style={{
          position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)",
          color: "var(--ink-4)", fontSize: 13, pointerEvents: "none",
        }}>🔍</span>
        <input
          type="text" placeholder="Search name or symbol…"
          value={search} onChange={e => setSearch(e.target.value)}
          style={{
            width: "100%", padding: "7px 10px 7px 30px",
            borderRadius: 9, border: "1px solid var(--hairline-strong)",
            background: "var(--surface)", color: "var(--ink)",
            fontSize: 13.5, outline: "none", boxSizing: "border-box",
          }}
        />
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────────────────
   Main screen
   ────────────────────────────────────────────────────────── */

function CryptoMarkets() {
  const markets = window.KAIRO && window.KAIRO.markets;
  const [sort,   setSort]   = useState("rank");
  const [search, setSearch] = useState("");

  const projects = useMemo(() => {
    if (!markets || !markets.projects) return [];
    let arr = [...markets.projects];
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      arr = arr.filter(p =>
        (p.name   || "").toLowerCase().includes(q) ||
        (p.symbol || "").toLowerCase().includes(q) ||
        (p.ecosystem_category || "").toLowerCase().includes(q)
      );
    }
    if (sort === "rank") arr.sort((a, b) => a.rank - b.rank);
    else arr.sort((a, b) => parseFloat(b[sort] || -Infinity) - parseFloat(a[sort] || -Infinity));
    return arr;
  }, [markets, sort, search]);

  /* ── Empty / loading states ── */
  if (!markets || !markets.projects) {
    return (
      <div className="screen-enter" style={{ padding: "60px 0", textAlign: "center" }}>
        <div style={{ fontSize: 40, marginBottom: 14 }}>📊</div>
        <h3 style={{ fontWeight: 800, fontSize: 20, color: "var(--ink)", marginBottom: 10 }}>
          Markets not loaded yet
        </h3>
        <p style={{ fontSize: 14, color: "var(--ink-3)", maxWidth: 420, margin: "0 auto 24px", lineHeight: 1.65 }}>
          Head to the <strong>Admin tab → Markets Data</strong> section, add your free
          CoinMarketCap key, and click <strong>Refresh Markets Data</strong>.
          Then click <strong>Run AI Analysis</strong> to get beginner-friendly explanations.
        </p>
        <div style={{
          display: "inline-block", padding: "14px 22px", borderRadius: 12,
          background: "var(--surface-2)", border: "1px solid var(--hairline)",
          fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--ink-3)",
          textAlign: "left", lineHeight: 2,
        }}>
          <span style={{ color: "var(--ink-4)" }}># step 1 — fetch prices from CoinMarketCap</span><br />
          python -m app.ingestion.crypto_markets<br />
          <span style={{ color: "var(--ink-4)" }}># step 2 — generate AI summaries</span><br />
          python -m app.markets.analyzer
        </div>
      </div>
    );
  }

  const analysisCount = projects.filter(p => p.description).length;
  const total         = (markets.projects || []).length;
  const updatedAt     = markets.updated_at
    ? new Date(markets.updated_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div className="screen-enter">
      {/* ── Page header ── */}
      <div style={{ marginBottom: 22 }}>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Live Markets</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 8 }}>
          <h2 style={{ fontSize: 26, fontWeight: 800, letterSpacing: "-0.02em", margin: 0 }}>
            Top 20 Crypto Projects
          </h2>
          {updatedAt && (
            <span className="mono" style={{ fontSize: 12, color: "var(--ink-4)" }}>
              prices updated {updatedAt}
            </span>
          )}
        </div>

        {/* Status chips */}
        <div style={{ display: "flex", gap: 7, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
          <span style={{ fontSize: 13, color: "var(--ink-3)" }}>
            Ranked by market cap · click any card for details
          </span>
          {analysisCount === total && total > 0 && (
            <span style={{
              fontSize: 11.5, fontWeight: 700, padding: "2px 9px", borderRadius: 99,
              background: "var(--c-sage)", color: "var(--c-sage-ink)",
            }}>✓ AI summaries loaded</span>
          )}
          {analysisCount > 0 && analysisCount < total && (
            <span style={{
              fontSize: 11.5, fontWeight: 600, padding: "2px 9px", borderRadius: 99,
              background: "var(--c-peach)", color: "var(--c-peach-ink)",
            }}>AI summaries: {analysisCount}/{total}</span>
          )}
          {analysisCount === 0 && (
            <span style={{
              fontSize: 11.5, fontWeight: 600, padding: "2px 9px", borderRadius: 99,
              background: "var(--surface-2)", color: "var(--ink-4)",
            }}>AI summaries not yet run</span>
          )}
          {markets.stale && (
            <span style={{
              fontSize: 11.5, fontWeight: 600, padding: "2px 9px", borderRadius: 99,
              background: "oklch(0.95 0.030 52)", color: "oklch(0.50 0.10 52)",
            }}>⚠ prices may be outdated</span>
          )}
        </div>

        <Toolbar sort={sort} setSort={setSort} search={search} setSearch={setSearch} />
      </div>

      {/* ── Card list ── */}
      {projects.length === 0 && search ? (
        <div style={{ padding: "40px 0", textAlign: "center", color: "var(--ink-3)", fontSize: 14 }}>
          No projects match "{search}"
        </div>
      ) : (
        projects.map(p => <MarketCard key={p.cmc_id || p.symbol} project={p} />)
      )}

      {/* ── Footer hint ── */}
      <div style={{
        marginTop: 24, padding: "13px 18px", borderRadius: 12,
        background: "var(--surface-2)", border: "1px solid var(--hairline)",
        fontSize: 12.5, color: "var(--ink-4)", lineHeight: 1.65,
      }}>
        <strong style={{ color: "var(--ink-3)" }}>Keep this fresh:</strong> run
        <code style={{ fontFamily: "var(--font-mono)", background: "var(--surface)", padding: "1px 6px", borderRadius: 5, margin: "0 4px" }}>
          python -m app.ingestion.crypto_markets
        </code>
        daily to refresh prices, then
        <code style={{ fontFamily: "var(--font-mono)", background: "var(--surface)", padding: "1px 6px", borderRadius: 5, margin: "0 4px" }}>
          python -m app.markets.analyzer
        </code>
        to refresh AI summaries. Or use the buttons in Admin → Markets.
      </div>
    </div>
  );
}

window.CryptoMarkets = CryptoMarkets;
