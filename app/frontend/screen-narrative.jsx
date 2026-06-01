/* ============================================================
   Kairo — Narratives (the ongoing "series" tracker)
   treatment variants: "timeline" | "arc"
   Per-tile drill-down with real supporting evidence
   ============================================================ */
const K = window.KAIRO;
let Icon, Asset, ForceTag, StatusBadge, CardLabel, StrengthCurve;

/* ---- phase & intent chips ---- */
const _PHASE_STYLE = {
  Discovery: { bg: "var(--c-denim)",  ink: "var(--c-denim-ink)" },
  Expanding: { bg: "var(--c-sage)",   ink: "var(--c-sage-ink)"  },
  Peak:      { bg: "var(--accent-soft)", ink: "var(--accent-ink)" },
  Maturing:  { bg: "var(--surface-2)", ink: "var(--ink-3)" },
  Declining: { bg: "var(--c-rose)",   ink: "var(--c-rose-ink)"  },
  Active:    { bg: "var(--c-peach)",  ink: "var(--c-peach-ink)" },
};
function PhaseChip({ phase }) {
  if (!phase) return null;
  const s = _PHASE_STYLE[phase] || { bg: "var(--surface-2)", ink: "var(--ink-3)" };
  return (
    <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
      background: s.bg, color: s.ink, borderRadius: 99, padding: "2px 9px", display: "inline-block" }}>
      {phase}
    </span>
  );
}

const _INTENT_STYLE = {
  Deploying:    { bg: "var(--c-sage)",  ink: "var(--c-sage-ink)"  },
  Positioning:  { bg: "var(--c-lav)",   ink: "var(--c-lav-ink)"   },
  Accumulating: { bg: "var(--c-denim)", ink: "var(--c-denim-ink)" },
  Rotating:     { bg: "var(--c-peach)", ink: "var(--c-peach-ink)" },
  Exiting:      { bg: "var(--c-rose)",  ink: "var(--c-rose-ink)"  },
};
function SmartIntentBadge({ intent }) {
  if (!intent) return null;
  const s = _INTENT_STYLE[intent] || { bg: "var(--surface-2)", ink: "var(--ink-2)" };
  return (
    <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase",
      background: s.bg, color: s.ink, borderRadius: 99, padding: "2px 9px", display: "inline-block" }}>
      Smart money · {intent}
    </span>
  );
}

/* ---- investor briefing sections (detail view) ---- */
function BriefingSections({ t }) {
  const { what_happening, why_matters, risk_note, watch_for } = t;
  if (!what_happening && !why_matters && !risk_note && !watch_for) return null;
  return (
    <div style={{ marginTop: 24, paddingTop: 22, borderTop: "1px solid var(--hairline)",
      display: "flex", flexDirection: "column", gap: 20 }}>
      {what_happening && (
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>What is happening</div>
          <p style={{ fontSize: 16, color: "var(--ink-2)", lineHeight: 1.65 }}>{what_happening}</p>
        </div>
      )}
      {why_matters && (
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>Why it matters</div>
          <p style={{ fontSize: 15.5, color: "var(--ink-2)", lineHeight: 1.65 }}>{why_matters}</p>
        </div>
      )}
      {(risk_note || watch_for) && (
        <div>
          <div className="eyebrow" style={{ marginBottom: 10 }}>Risk factors & what to watch</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {risk_note && (
              <div style={{ display: "flex", gap: 10, alignItems: "flex-start",
                background: "color-mix(in oklch, var(--c-peach) 30%, var(--surface-2))",
                borderRadius: "var(--r-sm)", padding: "12px 14px",
                border: "1px solid color-mix(in oklch, var(--c-peach) 50%, transparent)" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "var(--c-peach-ink)", flexShrink: 0, paddingTop: 1 }}>Risk</span>
                <span style={{ fontSize: 14.5, color: "var(--ink-2)", lineHeight: 1.6 }}>{risk_note}</span>
              </div>
            )}
            {watch_for && (
              <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <span className="eyebrow" style={{ paddingTop: 3, flexShrink: 0 }}>Watch for</span>
                <span style={{ fontSize: 14.5, color: "var(--ink-2)", fontStyle: "italic", lineHeight: 1.6 }}>{watch_for}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---- live narratives rail (index) ---- */
function NarrativeRail({ onDrill }) {
  if (!K.narratives || K.narratives.length === 0) {
    return (
      <div>
        <CardLabel icon="narr">Live narratives Kairo is tracking</CardLabel>
        <div style={{
          padding: "48px 32px", textAlign: "center", background: "var(--surface)",
          border: "1px dashed var(--hairline-strong)", borderRadius: "var(--r-lg)",
        }}>
          <div style={{ fontSize: 17, fontWeight: 600, color: "var(--ink-3)", marginBottom: 10 }}>
            No narratives detected yet
          </div>
          <p style={{ fontSize: 14.5, color: "var(--ink-4)", maxWidth: "36ch", margin: "0 auto" }}>
            Click <strong style={{ color: "var(--ink-3)" }}>Refresh / Run Detection</strong> to analyse current on-chain signals and surface emerging narratives.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <CardLabel icon="narr">Live narratives Kairo is tracking</CardLabel>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "var(--gap)" }}>
        {K.narratives.map(n => (
          <button key={n.id} onClick={() => onDrill(n.id)} className="card" style={{
            padding: 18, textAlign: "left", transition: "transform 0.18s, box-shadow 0.18s",
            width: "100%",
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
              <ForceTag id={n.force} size="sm" />
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>Day {n.day}</span>
            </div>
            <h3 style={{ fontSize: 16, fontWeight: 700, marginBottom: 6, lineHeight: 1.3 }}>{n.title}</h3>
            {(n.phase || n.summary_line) && (
              <div style={{ marginBottom: 10, display: "flex", flexDirection: "column", gap: 5 }}>
                {n.phase && <PhaseChip phase={n.phase} />}
                {n.summary_line && (
                  <p style={{ fontSize: 13, color: "var(--ink-3)", lineHeight: 1.5, margin: 0 }}>{n.summary_line}</p>
                )}
              </div>
            )}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
              <StatusBadge status={n.status} size="sm" />
              <span className="mono" style={{ fontSize: 15, fontWeight: 700, color: "var(--ink)" }}>{n.strength.toFixed(1)}</span>
            </div>
            {n.assets && n.assets.length > 0 && (
              <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 10 }}>
                {n.assets.map(a => <Asset key={a} sym={a} />)}
              </div>
            )}
            {n.smart_money_intent && (
              <div style={{ marginBottom: 8 }}>
                <SmartIntentBadge intent={n.smart_money_intent} />
              </div>
            )}
            <div style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--accent-ink)", fontSize: 13, fontWeight: 600, marginTop: 4 }}>
              View detail <Icon name="arrowR" size={13} stroke={2} />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ---- tracker header ---- */
function TrackerHeader({ t }) {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, flexWrap: "wrap" }}>
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 7, background: "var(--ink)", color: "var(--paper)",
              borderRadius: 99, padding: "5px 13px", fontSize: 13, fontWeight: 700,
            }} className="mono">Day {t.day || "—"}</span>
            <StatusBadge status={t.status} />
            {t.phase && <PhaseChip phase={t.phase} />}
            {t.smart_money_intent && <SmartIntentBadge intent={t.smart_money_intent} />}
            {t.category && (
              <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-3)", background: "var(--surface-2)",
                borderRadius: 99, padding: "3px 9px", border: "1px solid var(--hairline)" }}>
                {t.category}
              </span>
            )}
          </div>
          <h1 style={{ fontSize: "clamp(22px, 2.8vw, 32px)", fontWeight: 800, letterSpacing: "-0.02em", lineHeight: 1.2 }}>{t.title}</h1>
        </div>
        <StrengthDial value={t.strength || 0} delta={t.delta || "+0.0"} />
      </div>
      <p style={{ fontSize: 16, color: "var(--ink-2)", marginTop: 16, lineHeight: 1.65, maxWidth: "64ch" }}>{t.summary}</p>
      {(t.forces && t.forces.length > 0 || t.assets && t.assets.length > 0) && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 18, marginTop: 20, alignItems: "center" }}>
          {t.forces && t.forces.length > 0 && (
            <div style={{ display: "flex", gap: 8 }}>{t.forces.map(f => <ForceTag key={f} id={f} size="sm" />)}</div>
          )}
          {t.forces && t.forces.length > 0 && t.assets && t.assets.length > 0 && (
            <span style={{ width: 1, height: 22, background: "var(--hairline)" }} />
          )}
          {t.assets && t.assets.length > 0 && (
            <div style={{ display: "flex", gap: 7 }}>{t.assets.map(a => <Asset key={a} sym={a} tone="accent" />)}</div>
          )}
        </div>
      )}
    </div>
  );
}

function StrengthDial({ value, delta }) {
  const pct = Math.max(0, Math.min(1, value / 10));
  const r = 34, c = 2 * Math.PI * r;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 14, flexShrink: 0 }}>
      <div style={{ position: "relative", width: 84, height: 84 }}>
        <svg viewBox="0 0 84 84" width="84" height="84">
          <circle cx="42" cy="42" r={r} fill="none" stroke="var(--hairline)" strokeWidth="7" />
          <circle cx="42" cy="42" r={r} fill="none" stroke="var(--accent)" strokeWidth="7" strokeLinecap="round"
            strokeDasharray={c} strokeDashoffset={c * (1 - pct)} transform="rotate(-90 42 42)" />
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center" }}>
          <span className="mono" style={{ fontSize: 20, fontWeight: 700, color: "var(--ink)" }}>{value.toFixed(1)}</span>
        </div>
      </div>
      <div>
        <div className="eyebrow">Trend strength</div>
        <div style={{ fontSize: 13.5, color: "var(--pos)", fontWeight: 700, marginTop: 4 }}>{delta} this week</div>
      </div>
    </div>
  );
}

/* ---- episode (timeline node) ---- */
function Episode({ ep, last }) {
  const f = (K.forces && K.forces[ep.force]) || { color: "sage" };
  return (
    <div style={{ display: "flex", gap: 18, position: "relative" }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
        <span style={{
          width: 14, height: 14, borderRadius: 99, background: `var(--c-${f.color}-ink)`,
          boxShadow: `0 0 0 4px var(--c-${f.color})`, marginTop: 5, zIndex: 1,
        }} />
        {!last && <span style={{ flex: 1, width: 2, background: "var(--hairline)", marginTop: 4 }} />}
      </div>
      <div style={{ paddingBottom: last ? 0 : 26, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 7 }}>
          <span className="mono" style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink-3)" }}>Day {ep.day} · {ep.date}</span>
          <ForceTag id={ep.force} size="sm" />
        </div>
        <h3 style={{ fontSize: 16, fontWeight: 700, lineHeight: 1.3 }}>{ep.headline}</h3>
        <p style={{ fontSize: 14.5, color: "var(--ink-2)", marginTop: 7, lineHeight: 1.6 }}>{ep.body}</p>
      </div>
    </div>
  );
}

/* ---- Supporting facts: whale move card ---- */
function WhaleCard({ m }) {
  return (
    <div style={{
      background: "var(--surface-2)", borderRadius: "var(--r-md)", padding: "16px 18px",
      border: "1px solid var(--hairline)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <div>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
            color: "var(--ink-3)", display: "block", marginBottom: 4 }}>{m.tier}</span>
          <span className="mono" style={{ fontSize: 22, fontWeight: 800, color: "var(--ink)" }}>{m.usd_fmt}</span>
        </div>
        <span style={{
          background: "var(--accent-soft)", color: "var(--accent-ink)",
          padding: "3px 10px", borderRadius: 99, fontSize: 13, fontWeight: 700,
        }}>{m.symbol}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 16px", marginTop: 10 }}>
        <FactRow label="From" value={m.wallet_from} mono />
        <FactRow label="To" value={m.wallet_to} mono />
        {m.amount > 0 && <FactRow label="Amount" value={`${m.amount.toLocaleString(undefined, {maximumFractionDigits: 2})} ${m.symbol}`} />}
        {m.tx_hash && <FactRow label="Tx hash" value={m.tx_hash} mono link={m.etherscan_url} />}
      </div>
    </div>
  );
}

/* ---- Smart money wallet card ---- */
function SmartMoneyCard({ w }) {
  return (
    <div style={{
      background: "var(--surface-2)", borderRadius: "var(--r-md)", padding: "16px 18px",
      border: "1px solid var(--hairline)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <span className="mono" style={{ fontSize: 13, color: "var(--ink-3)", fontWeight: 600 }}>{w.wallet}</span>
        <span style={{
          background: "var(--accent-soft)", color: "var(--accent-ink)",
          padding: "3px 10px", borderRadius: 99, fontSize: 13, fontWeight: 700,
        }}>{w.symbol}</span>
      </div>
      <div className="mono" style={{ fontSize: 21, fontWeight: 800, color: "var(--ink)", marginBottom: 8 }}>{w.usd_fmt}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 20px" }}>
        {w.signal && <FactRow label="Signal" value={w.signal} />}
        {w.buy_count > 0 && <FactRow label="Buy txs" value={w.buy_count} />}
        {w.wallets_buying_same > 0 && <FactRow label="Wallets buying same" value={w.wallets_buying_same.toLocaleString()} />}
      </div>
    </div>
  );
}

/* ---- Bridge flow card ---- */
function BridgeCard({ b }) {
  return (
    <div style={{
      background: "var(--surface-2)", borderRadius: "var(--r-md)", padding: "16px 18px",
      border: "1px solid var(--hairline)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <div>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
            color: "var(--ink-3)", display: "block", marginBottom: 4 }}>{b.bridge}</span>
          <span className="mono" style={{ fontSize: 22, fontWeight: 800, color: "var(--ink)" }}>{b.usd_fmt}</span>
        </div>
      </div>
      <p style={{ fontSize: 14, color: "var(--ink-2)", marginBottom: 10, fontWeight: 500 }}>{b.direction}</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 20px" }}>
        {b.signal && <FactRow label="Signal" value={b.signal} />}
        {b.tx_count > 0 && <FactRow label="Transactions" value={b.tx_count} />}
        {b.wallets > 0 && <FactRow label="Unique wallets" value={b.wallets} />}
      </div>
    </div>
  );
}

/* ---- Volume spike card ---- */
function SpikeCard({ s }) {
  return (
    <div style={{
      background: "var(--surface-2)", borderRadius: "var(--r-md)", padding: "16px 18px",
      border: "1px solid var(--hairline)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
        <span style={{
          background: "var(--accent-soft)", color: "var(--accent-ink)",
          padding: "3px 10px", borderRadius: 99, fontSize: 14, fontWeight: 800,
        }}>{s.symbol}</span>
        <span className="mono" style={{ fontSize: 20, fontWeight: 800, color: "var(--ink)" }}>{s.multiplier.toFixed(2)}×</span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 20px", marginTop: 6 }}>
        {s.signal && <FactRow label="Signal" value={s.signal} />}
        {s.current_vol > 0 && <FactRow label="Volume" value={s.current_vol_fmt} />}
        {s.traders > 0 && <FactRow label="Traders" value={s.traders.toLocaleString()} />}
      </div>
    </div>
  );
}

/* ---- Wallet concentration row ---- */
function ConcentrationRow({ w, last }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 14, padding: "11px 0",
      borderBottom: last ? "none" : "1px solid var(--hairline)",
    }}>
      <span className="mono" style={{ fontSize: 13, fontWeight: 700, color: "var(--ink-3)", width: 24, flexShrink: 0 }}>#{w.rank}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <span className="mono" style={{ fontSize: 13, color: "var(--ink-2)" }}>{w.address}</span>
        {w.label && w.label !== "Unknown" && (
          <span style={{ marginLeft: 8, fontSize: 12, color: "var(--ink-3)" }}>({w.label})</span>
        )}
      </div>
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <span className="mono" style={{ fontSize: 14, fontWeight: 700, color: "var(--ink)" }}>
          {w.pct.toFixed(2)}%
        </span>
        <span style={{ fontSize: 12, color: "var(--ink-3)", display: "block" }}>
          Cumulative {w.cumulative_pct.toFixed(1)}%
        </span>
      </div>
    </div>
  );
}

/* ---- Generic label/value pair ---- */
function FactRow({ label, value, mono, link }) {
  const val = link
    ? <a href={link} target="_blank" rel="noopener noreferrer"
        style={{ color: "var(--accent-ink)", textDecoration: "underline", fontFamily: mono ? "var(--font-mono)" : "inherit" }}>{value}</a>
    : <span style={{ fontFamily: mono ? "var(--font-mono)" : "inherit" }}>{value}</span>;
  return (
    <div style={{ minWidth: 0 }}>
      <div className="eyebrow" style={{ marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-2)" }}>{val}</div>
    </div>
  );
}

/* ---- Supporting evidence section ---- */
function SupportingEvidence({ facts, assets }) {
  if (!facts) return null;
  const assetSet = new Set((assets || []).map(a => a.toUpperCase()));
  const filterBySymbol = (arr) =>
    assetSet.size > 0
      ? (arr || []).filter(r => assetSet.has((r.symbol || "").toUpperCase()))
      : (arr || []);

  const whales  = filterBySymbol(facts.whale_moves);
  const smart   = filterBySymbol(facts.smart_money_wallets);
  const spikes  = filterBySymbol(facts.volume_spikes);
  const bridges = facts.bridge_flows || [];
  const conc    = facts.wallet_concentration || [];

  const hasWhales = whales.length > 0;
  const hasSmart  = smart.length > 0;
  const hasBridge = bridges.length > 0;
  const hasSpikes = spikes.length > 0;
  const hasConc   = conc.length > 0;

  if (!hasWhales && !hasSmart && !hasBridge && !hasSpikes && !hasConc) {
    return (
      <div style={{ marginTop: 28, paddingTop: 24, borderTop: "1px solid var(--hairline)" }}>
        <CardLabel icon="watch">Supporting evidence</CardLabel>
        <p style={{ fontSize: 14.5, color: "var(--ink-3)" }}>
          No on-chain evidence loaded yet. Run detection to fetch live signal data.
        </p>
      </div>
    );
  }

  return (
    <div style={{ marginTop: 28, paddingTop: 24, borderTop: "1px solid var(--hairline)", display: "flex", flexDirection: "column", gap: 28 }}>
      <CardLabel icon="watch">Supporting on-chain evidence</CardLabel>

      {hasWhales && (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <Icon name="brain" size={15} stroke={1.8} style={{ color: "var(--ink-3)" }} />
            <span className="eyebrow">Large whale transactions</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
            {whales.map((m, i) => <WhaleCard key={i} m={m} />)}
          </div>
        </div>
      )}

      {hasSmart && (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <Icon name="brain" size={15} stroke={1.8} style={{ color: "var(--ink-3)" }} />
            <span className="eyebrow">Smart money accumulation</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
            {smart.map((w, i) => <SmartMoneyCard key={i} w={w} />)}
          </div>
        </div>
      )}

      {hasBridge && (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <Icon name="swap" size={15} stroke={1.8} style={{ color: "var(--ink-3)" }} />
            <span className="eyebrow">Bridge capital flows</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
            {bridges.map((b, i) => <BridgeCard key={i} b={b} />)}
          </div>
        </div>
      )}

      {hasSpikes && (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <Icon name="spark2" size={15} stroke={1.8} style={{ color: "var(--ink-3)" }} />
            <span className="eyebrow">Volume anomalies</span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 12 }}>
            {spikes.map((s, i) => <SpikeCard key={i} s={s} />)}
          </div>
        </div>
      )}

      {hasConc && (
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <Icon name="watch" size={15} stroke={1.8} style={{ color: "var(--ink-3)" }} />
            <span className="eyebrow">Top holder concentration</span>
          </div>
          <div style={{ background: "var(--surface-2)", borderRadius: "var(--r-md)", padding: "4px 18px", border: "1px solid var(--hairline)" }}>
            {conc.map((w, i, arr) => (
              <ConcentrationRow key={i} w={w} last={i === arr.length - 1} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ---- drill-down detail view ---- */
function NarrativeDetail({ narrativeId, treatment, onBack }) {
  const t = (K.trackers && K.trackers[narrativeId]) || K.tracker;
  return (
    <div className="screen-enter" style={{ display: "flex", flexDirection: "column", gap: "calc(var(--gap) + 10px)" }}>
      <button onClick={onBack} style={{
        display: "inline-flex", alignItems: "center", gap: 8, alignSelf: "flex-start",
        color: "var(--ink-3)", fontSize: 14, fontWeight: 600, padding: "8px 14px",
        border: "1px solid var(--hairline)", borderRadius: "var(--r-sm)",
        background: "var(--surface)", boxShadow: "var(--shadow-soft)",
      }}>
        <Icon name="arrowR" size={14} stroke={2} style={{ transform: "rotate(180deg)" }} />
        Back to narratives
      </button>

      <article className="card" style={{ padding: "calc(var(--card-pad) + 4px)" }}>
        <TrackerHeader t={t} />

        {treatment === "arc" && t.curve && t.curve.length > 0 && (
          <div style={{ marginTop: 26 }}>
            <CardLabel icon="history" right={<span style={{ fontSize: 13, color: "var(--ink-3)" }}>14-day strength arc</span>}>Story arc</CardLabel>
            <div style={{ background: "var(--surface-2)", borderRadius: "var(--r-md)", padding: "20px 18px 8px" }}>
              <StrengthCurve data={t.curve} />
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
                <span className="mono" style={{ fontSize: 12, color: "var(--ink-4)" }}>Day 1</span>
                <span className="mono" style={{ fontSize: 12, color: "var(--ink-4)" }}>Today</span>
              </div>
            </div>
          </div>
        )}

        {t.episodes && t.episodes.length > 0 && (
          <div style={{ marginTop: 28, paddingTop: 24, borderTop: "1px solid var(--hairline)" }}>
            <CardLabel icon="narr">{treatment === "arc" ? "Key moments" : "The story so far"}</CardLabel>
            <div style={{ marginTop: 6 }}>
              {(treatment === "arc" ? t.episodes.slice(0, 3) : t.episodes).map((ep, i, arr) => (
                <Episode key={`${ep.day}-${i}`} ep={ep} last={i === arr.length - 1} />
              ))}
            </div>
            {treatment === "arc" && t.episodes.length > 3 && (
              <button style={{ marginTop: 6, color: "var(--accent-ink)", fontSize: 14, fontWeight: 600,
                display: "inline-flex", alignItems: "center", gap: 6 }}>
                See all {t.episodes.length} moments <Icon name="chevron" size={15} stroke={2} />
              </button>
            )}
          </div>
        )}

        <SupportingEvidence facts={t.supportingFacts} assets={t.assets} />
      </article>
    </div>
  );
}

/* ---- main component ---- */
function NarrativeTracker({ treatment, activeId, onSelect }) {
  ({ Icon, Asset, ForceTag, StatusBadge, CardLabel, StrengthCurve } = window);
  const { useState } = React;
  const [drillId, setDrillId] = useState(null);

  if (drillId) {
    return (
      <NarrativeDetail
        narrativeId={drillId}
        treatment={treatment}
        onBack={() => setDrillId(null)}
      />
    );
  }

  return (
    <div className="screen-enter" style={{ display: "flex", flexDirection: "column", gap: "calc(var(--gap) + 10px)" }}>
      <NarrativeRail onDrill={(id) => { onSelect(id); setDrillId(id); }} />
    </div>
  );
}

Object.assign(window, { NarrativeTracker });
