/* ============================================================
   Kairo — Markets screen: top 20 crypto by market cap
   ============================================================ */
const { useState, useMemo } = React;

/* ---- helpers ---- */

function PerfCell({ value }) {
  if (value === null || value === undefined) {
    return <span style={{ color: "var(--ink-4)", fontFamily: "var(--font-mono)" }}>—</span>;
  }
  const num = parseFloat(value);
  const pos = num >= 0;
  const color = pos ? "var(--pos)" : "oklch(0.55 0.12 22)";
  return (
    <span className="mono" style={{ color, fontWeight: 600, fontSize: 13.5 }}>
      {pos ? "+" : ""}{num.toFixed(2)}%
    </span>
  );
}

function PriceCell({ value }) {
  if (!value && value !== 0) return <span style={{ color: "var(--ink-4)" }}>—</span>;
  const num = parseFloat(value);
  let fmt;
  if (num >= 1000) fmt = "$" + num.toLocaleString("en-US", { maximumFractionDigits: 0 });
  else if (num >= 1) fmt = "$" + num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  else if (num >= 0.01) fmt = "$" + num.toFixed(4);
  else fmt = "$" + num.toFixed(6);
  return <span className="mono" style={{ color: "var(--ink)", fontWeight: 500, fontSize: 13.5 }}>{fmt}</span>;
}

function McapCell({ value }) {
  if (!value && value !== 0) return <span style={{ color: "var(--ink-4)" }}>—</span>;
  const num = parseFloat(value);
  let fmt;
  if (num >= 1e12) fmt = "$" + (num / 1e12).toFixed(2) + "T";
  else if (num >= 1e9) fmt = "$" + (num / 1e9).toFixed(1) + "B";
  else if (num >= 1e6) fmt = "$" + (num / 1e6).toFixed(0) + "M";
  else fmt = "$" + num.toLocaleString("en-US");
  return <span className="mono" style={{ color: "var(--ink-3)", fontSize: 13 }}>{fmt}</span>;
}

function RoadmapButton({ url, name, isAuto }) {
  if (!url) return <span style={{ color: "var(--ink-4)", fontSize: 12 }}>—</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title={isAuto ? `Auto-discovered roadmap for ${name}` : `${name} website`}
      style={{
        display: "inline-flex", alignItems: "center", gap: 4,
        padding: "3px 10px 3px 8px", borderRadius: 7,
        background: "var(--surface-2)", border: "1px solid var(--hairline)",
        color: "var(--accent-ink)", fontSize: 12.5, fontWeight: 600,
        textDecoration: "none", transition: "background 0.12s",
        whiteSpace: "nowrap",
      }}
      onMouseEnter={e => e.currentTarget.style.background = "var(--accent-soft)"}
      onMouseLeave={e => e.currentTarget.style.background = "var(--surface-2)"}
    >
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3" />
      </svg>
      {isAuto ? "Roadmap" : "Site"}
    </a>
  );
}

function CryptoLogo({ symbol, logoUrl, size = 30 }) {
  const [err, setErr] = useState(false);
  const COLORS = ["#E8967A","#7B9FE0","#7BC4AA","#C4A97B","#9B7BC4","#7BC4C4","#C47B9B","#B4C47B"];
  const bg = COLORS[(symbol || "?").charCodeAt(0) % COLORS.length];
  if (logoUrl && !err) {
    return (
      <img
        src={logoUrl} alt={symbol} width={size} height={size}
        style={{ borderRadius: "50%", display: "block", flexShrink: 0 }}
        onError={() => setErr(true)}
      />
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

function SortArrow({ dir }) {
  if (!dir) return <span style={{ opacity: 0.3, marginLeft: 3, fontSize: 10 }}>⇅</span>;
  return <span style={{ color: "var(--accent-ink)", marginLeft: 3, fontSize: 10 }}>{dir === "asc" ? "↑" : "↓"}</span>;
}

/* ---- main component ---- */

function CryptoMarkets() {
  const markets = window.KAIRO && window.KAIRO.markets;
  const [sortKey, setSortKey] = useState("rank");
  const [sortDir, setSortDir] = useState("asc");

  const projects = useMemo(() => {
    if (!markets || !markets.projects || !markets.projects.length) return [];
    const arr = [...markets.projects];
    arr.sort((a, b) => {
      let av = a[sortKey], bv = b[sortKey];
      if (typeof av === "string") { av = av.toLowerCase(); bv = (bv || "").toLowerCase(); }
      if (av == null) av = sortDir === "asc" ? Infinity : -Infinity;
      if (bv == null) bv = sortDir === "asc" ? Infinity : -Infinity;
      return sortDir === "asc" ? (av > bv ? 1 : av < bv ? -1 : 0) : (av < bv ? 1 : av > bv ? -1 : 0);
    });
    return arr;
  }, [markets, sortKey, sortDir]);

  function toggleSort(key) {
    if (sortKey === key) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(key); setSortDir(key === "rank" || key === "name" ? "asc" : "desc"); }
  }

  const thStyle = (key, right = false, extra = {}) => ({
    padding: "10px 14px",
    textAlign: right ? "right" : "left",
    fontSize: 11.5,
    fontWeight: 700,
    color: sortKey === key ? "var(--accent-ink)" : "var(--ink-3)",
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    cursor: "pointer",
    userSelect: "none",
    whiteSpace: "nowrap",
    borderBottom: "1px solid var(--hairline)",
    background: "var(--surface)",
    position: "sticky",
    top: 0,
    zIndex: 2,
    ...extra,
  });

  const updatedAt = markets && markets.updated_at
    ? new Date(markets.updated_at).toLocaleString("en-US", {
        month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
      })
    : null;

  /* ── empty states ── */
  if (!markets || !markets.projects) {
    return (
      <div className="screen-enter" style={{ padding: "60px 0", textAlign: "center" }}>
        <div style={{ fontSize: 32, marginBottom: 14 }}>📊</div>
        <div style={{ fontSize: 16, fontWeight: 700, color: "var(--ink)", marginBottom: 8 }}>
          Markets data not loaded yet
        </div>
        <p style={{ fontSize: 14, color: "var(--ink-3)", maxWidth: 440, margin: "0 auto 20px" }}>
          Run the daily update script once to populate this tab. You'll need a free CoinMarketCap API key.
        </p>
        <div style={{
          display: "inline-block", padding: "12px 20px", borderRadius: 10,
          background: "var(--surface-2)", border: "1px solid var(--hairline)",
          fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--ink-2)", textAlign: "left",
        }}>
          <div style={{ color: "var(--ink-4)", fontSize: 11, marginBottom: 4 }}># get free key → coinmarketcap.com/api/</div>
          <div>python -m app.ingestion.crypto_markets</div>
        </div>
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="screen-enter" style={{ padding: "60px 0", textAlign: "center" }}>
        <div style={{ fontSize: 15, color: "var(--ink-3)" }}>No project data — run the update script.</div>
      </div>
    );
  }

  return (
    <div className="screen-enter">
      {/* ── Header ── */}
      <div style={{ marginBottom: 28 }}>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Live Markets</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
          <h2 style={{ fontSize: 26, fontWeight: 800, letterSpacing: "-0.02em", margin: 0 }}>
            Top 20 Crypto Projects
          </h2>
          {updatedAt && (
            <span className="mono" style={{ fontSize: 12.5, color: "var(--ink-4)" }}>
              updated {updatedAt}
            </span>
          )}
          {markets.stale && (
            <span style={{
              fontSize: 12, fontWeight: 600, color: "oklch(0.56 0.10 52)",
              background: "oklch(0.95 0.03 52)", padding: "2px 9px", borderRadius: 99,
            }}>
              outdated — refresh recommended
            </span>
          )}
        </div>
        <p style={{ marginTop: 6, color: "var(--ink-3)", fontSize: 14 }}>
          Ranked by market cap &nbsp;·&nbsp; 1d / 7d / 30d performance &nbsp;·&nbsp; Roadmap links auto-discovered from official sites
        </p>
      </div>

      {/* ── Table ── */}
      <div className="card" style={{ overflow: "hidden" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 860 }}>
            <thead>
              <tr>
                <th onClick={() => toggleSort("rank")} style={thStyle("rank", false, { width: 52, paddingLeft: 22 })}>
                  # <SortArrow dir={sortKey === "rank" ? sortDir : null} />
                </th>
                <th onClick={() => toggleSort("name")} style={thStyle("name")}>
                  Project <SortArrow dir={sortKey === "name" ? sortDir : null} />
                </th>
                <th onClick={() => toggleSort("price_usd")} style={thStyle("price_usd", true)}>
                  Price <SortArrow dir={sortKey === "price_usd" ? sortDir : null} />
                </th>
                <th onClick={() => toggleSort("perf_1d")} style={thStyle("perf_1d", true)}>
                  1 Day <SortArrow dir={sortKey === "perf_1d" ? sortDir : null} />
                </th>
                <th onClick={() => toggleSort("perf_7d")} style={thStyle("perf_7d", true)}>
                  7 Days <SortArrow dir={sortKey === "perf_7d" ? sortDir : null} />
                </th>
                <th onClick={() => toggleSort("perf_30d")} style={thStyle("perf_30d", true)}>
                  30 Days <SortArrow dir={sortKey === "perf_30d" ? sortDir : null} />
                </th>
                <th onClick={() => toggleSort("market_cap")} style={thStyle("market_cap", true)}>
                  Mkt Cap <SortArrow dir={sortKey === "market_cap" ? sortDir : null} />
                </th>
                <th style={{ ...thStyle(null, false), cursor: "default", textAlign: "center", width: 120 }}>
                  Roadmap
                </th>
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr
                  key={p.cmc_id || p.symbol}
                  style={{ borderBottom: "1px solid var(--hairline)", transition: "background 0.1s" }}
                  onMouseEnter={e => e.currentTarget.style.background = "color-mix(in oklch, var(--surface-2) 70%, transparent)"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                >
                  <td style={{ padding: "13px 10px 13px 22px", width: 52 }}>
                    <span className="mono" style={{ color: "var(--ink-4)", fontSize: 13, fontWeight: 500 }}>
                      {p.rank}
                    </span>
                  </td>
                  <td style={{ padding: "13px 14px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <CryptoLogo symbol={p.symbol} logoUrl={p.logo_url} size={30} />
                      <div>
                        <div style={{ fontWeight: 700, fontSize: 14, color: "var(--ink)", lineHeight: 1.2 }}>{p.name}</div>
                        <div className="mono" style={{ fontSize: 11, color: "var(--ink-4)", fontWeight: 500, marginTop: 1 }}>{p.symbol}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: "13px 14px", textAlign: "right" }}><PriceCell value={p.price_usd} /></td>
                  <td style={{ padding: "13px 14px", textAlign: "right" }}><PerfCell value={p.perf_1d} /></td>
                  <td style={{ padding: "13px 14px", textAlign: "right" }}><PerfCell value={p.perf_7d} /></td>
                  <td style={{ padding: "13px 14px", textAlign: "right" }}><PerfCell value={p.perf_30d} /></td>
                  <td style={{ padding: "13px 14px", textAlign: "right" }}><McapCell value={p.market_cap} /></td>
                  <td style={{ padding: "13px 14px", textAlign: "center" }}>
                    <RoadmapButton url={p.roadmap_url} name={p.name} isAuto={p.roadmap_url_auto} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* ── Table footer ── */}
        <div style={{
          padding: "10px 20px", borderTop: "1px solid var(--hairline)",
          background: "var(--surface-2)",
          display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8,
        }}>
          <span style={{ fontSize: 12, color: "var(--ink-4)" }}>
            Source: CoinMarketCap &nbsp;·&nbsp; {projects.length} projects &nbsp;·&nbsp; Click column headers to sort
          </span>
          <span style={{ fontSize: 12, color: "var(--ink-4)" }}>
            "Roadmap" = auto-discovered &nbsp;·&nbsp; "Site" = official website (no roadmap path found)
          </span>
        </div>
      </div>

      {/* ── Refresh hint ── */}
      <div style={{
        marginTop: 20, padding: "14px 20px", borderRadius: 12,
        background: "var(--surface-2)", border: "1px solid var(--hairline)",
      }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-2)", marginBottom: 4 }}>Keep this data fresh</div>
        <p style={{ fontSize: 12.5, color: "var(--ink-3)", lineHeight: 1.65, margin: 0 }}>
          Run daily to refresh rankings, prices, and auto-rediscover roadmap links as the top 20 changes:
          <br />
          <code style={{
            fontFamily: "var(--font-mono)", background: "var(--surface)", fontSize: 12,
            padding: "2px 8px", borderRadius: 5, color: "var(--ink-2)", marginTop: 4, display: "inline-block",
          }}>
            python -m app.ingestion.crypto_markets
          </code>
          &nbsp;&nbsp;
          <span style={{ color: "var(--ink-4)" }}>— or add to your cron / CI schedule</span>
        </p>
      </div>
    </div>
  );
}

window.CryptoMarkets = CryptoMarkets;
