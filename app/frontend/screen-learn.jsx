/* ============================================================
   Kairo — Crypto 101 screen
   Intelligent tile layout: anchor concepts anchor a row, related
   concepts fill the right. Click any tile for a description
   preview; "Full explanation" opens an in-app detail view.
   ============================================================ */
const { useState, useMemo } = React;

/* ── helpers ──────────────────────────────────────────────── */

function buildDisplayRows(concepts, groups) {
  if (!concepts || !concepts.length) return { rows: [], ungrouped: [] };

  const bySlug = {};
  concepts.forEach(c => { bySlug[c.concept_slug] = c; });

  const inGroup = new Set();
  const rows = [];

  (groups || []).forEach(g => {
    const anchor = bySlug[g.anchor_slug];
    if (!anchor) return;
    const related = (g.related_slugs || [])
      .map(s => bySlug[s])
      .filter(Boolean);
    inGroup.add(g.anchor_slug);
    related.forEach(c => inGroup.add(c.concept_slug));
    rows.push({ anchor, related });
  });

  const ungrouped = concepts.filter(c => !inGroup.has(c.concept_slug));
  return { rows, ungrouped };
}

/* ── Small / large concept tile ───────────────────────────── */

function ConceptTile({ concept, size, isExpanded, onToggle, onDetail }) {
  const isLg = size === "lg";
  return (
    <div
      onClick={() => onToggle(concept.concept_slug)}
      style={{
        cursor: "pointer",
        background: isExpanded ? "var(--accent-soft)" : "var(--surface)",
        border: "1px solid " + (isExpanded
          ? "color-mix(in oklch, var(--accent) 35%, transparent)"
          : "var(--hairline)"),
        borderRadius: 16,
        padding: isLg ? "24px 22px" : "18px 18px",
        display: "flex",
        flexDirection: "column",
        gap: isLg ? 10 : 8,
        transition: "background 0.15s, border-color 0.15s, box-shadow 0.15s",
        boxShadow: isExpanded
          ? "0 0 0 3px color-mix(in oklch, var(--accent) 12%, transparent)"
          : "var(--shadow-soft)",
        height: "100%",
        boxSizing: "border-box",
      }}
    >
      {/* emoji + name */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <span style={{ fontSize: isLg ? 28 : 22, lineHeight: 1, flexShrink: 0, marginTop: 1 }}>
          {concept.emoji || "🔗"}
        </span>
        <div>
          <div style={{
            fontSize: isLg ? 17 : 14.5,
            fontWeight: 800,
            color: "var(--ink)",
            letterSpacing: "-0.015em",
            lineHeight: 1.2,
          }}>
            {concept.concept_name}
          </div>
          {concept.key_takeaway && (
            <div style={{
              fontSize: isLg ? 12.5 : 11.5,
              color: "var(--ink-3)",
              marginTop: 4,
              lineHeight: 1.45,
              fontWeight: 500,
            }}>
              {concept.key_takeaway}
            </div>
          )}
        </div>
      </div>

      {/* expanded preview — stopPropagation so the outer toggle doesn't fire */}
      {isExpanded && (
        <div onClick={e => e.stopPropagation()} style={{ marginTop: 4 }}>
          <div style={{
            fontSize: 11, fontWeight: 700, letterSpacing: "0.09em",
            textTransform: "uppercase", color: "var(--accent-ink)",
            marginBottom: 5, fontFamily: "var(--font-mono)",
          }}>
            Plain English
          </div>
          <p style={{ fontSize: 13.5, color: "var(--ink-2)", lineHeight: 1.6, margin: 0 }}>
            {concept.plain_english}
          </p>
          <button
            onClick={() => onDetail(concept)}
            style={{
              marginTop: 12, padding: "7px 14px",
              background: "var(--accent)", color: "var(--paper)",
              border: "none", borderRadius: 8,
              fontSize: 12.5, fontWeight: 700, cursor: "pointer",
              display: "inline-flex", alignItems: "center", gap: 5,
              transition: "background 0.15s",
            }}
          >
            Full explanation →
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Grouped row: anchor left, related right ──────────────── */

function GroupRow({ anchor, related, expandedSlug, onToggle, onDetail }) {
  const hasRelated = related.length > 0;
  const visible = related.slice(0, 6);
  const cols = Math.min(visible.length, 3);

  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: hasRelated ? "minmax(220px, 1fr) 2fr" : "1fr",
      gap: 14,
      marginBottom: 18,
      alignItems: "start",
    }}>
      <ConceptTile
        concept={anchor}
        size="lg"
        isExpanded={expandedSlug === anchor.concept_slug}
        onToggle={onToggle}
        onDetail={onDetail}
      />
      {hasRelated && (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(" + cols + ", 1fr)",
          gap: 10,
        }}>
          {visible.map(c => (
            <ConceptTile
              key={c.concept_slug}
              concept={c}
              size="sm"
              isExpanded={expandedSlug === c.concept_slug}
              onToggle={onToggle}
              onDetail={onDetail}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Detail view ──────────────────────────────────────────── */

function ConceptDetail({ concept, onBack }) {
  const a = concept.traditional_analogy || {};
  return (
    <div className="screen-enter">
      {/* back button */}
      <button
        onClick={onBack}
        style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          marginBottom: 28, padding: "8px 14px",
          background: "var(--surface)", border: "1px solid var(--hairline)",
          borderRadius: 9, fontSize: 13.5, fontWeight: 600,
          color: "var(--ink-3)", cursor: "pointer",
        }}
      >
        ← Back to Crypto 101
      </button>

      {/* hero */}
      <div style={{ display: "flex", alignItems: "center", gap: 18, marginBottom: 28 }}>
        <span style={{
          fontSize: 52, lineHeight: 1,
          background: "var(--surface)", border: "1px solid var(--hairline)",
          borderRadius: 18, padding: "14px 18px",
          boxShadow: "var(--shadow-soft)",
        }}>
          {concept.emoji || "🔗"}
        </span>
        <div>
          <div className="eyebrow" style={{ marginBottom: 5 }}>Crypto 101</div>
          <h1 style={{ fontSize: 32, fontWeight: 800, letterSpacing: "-0.025em", marginBottom: 6 }}>
            {concept.concept_name}
          </h1>
          {concept.key_takeaway && (
            <div style={{ fontSize: 15, color: "var(--accent-ink)", fontWeight: 600 }}>
              {concept.key_takeaway}
            </div>
          )}
        </div>
      </div>

      {/* official definition */}
      <div className="card" style={{ padding: "22px 24px", marginBottom: 16 }}>
        <div style={{
          fontSize: 10.5, fontWeight: 700, letterSpacing: "0.10em",
          textTransform: "uppercase", color: "var(--ink-3)", marginBottom: 8,
          fontFamily: "var(--font-mono)",
        }}>
          Official Definition
        </div>
        <p style={{ fontSize: 15, color: "var(--ink-2)", lineHeight: 1.7 }}>
          {concept.real_description}
        </p>
      </div>

      {/* plain english */}
      <div style={{
        background: "var(--accent-soft)",
        border: "1px solid color-mix(in oklch, var(--accent) 22%, transparent)",
        borderRadius: 16, padding: "22px 24px", marginBottom: 16,
      }}>
        <div style={{
          fontSize: 10.5, fontWeight: 700, letterSpacing: "0.10em",
          textTransform: "uppercase", color: "var(--accent-ink)", marginBottom: 8,
          fontFamily: "var(--font-mono)",
        }}>
          In Plain English
        </div>
        <p style={{ fontSize: 16, color: "var(--ink)", lineHeight: 1.7, fontWeight: 500 }}>
          {concept.plain_english}
        </p>
      </div>

      {/* analogy */}
      <div className="card" style={{ padding: "22px 24px", marginBottom: 16 }}>
        <div style={{
          fontSize: 10.5, fontWeight: 700, letterSpacing: "0.10em",
          textTransform: "uppercase", color: "var(--ink-3)", marginBottom: 14,
          fontFamily: "var(--font-mono)",
        }}>
          Real-World Analogy
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <div style={{
            background: "var(--surface-2)", borderRadius: 12,
            padding: "16px 18px", border: "1px solid var(--hairline)",
          }}>
            <div style={{
              fontSize: 11, fontWeight: 700, color: "var(--ink-3)",
              textTransform: "uppercase", letterSpacing: "0.07em",
              marginBottom: 8, fontFamily: "var(--font-mono)",
            }}>
              How it works today
            </div>
            <p style={{ fontSize: 14, color: "var(--ink-2)", lineHeight: 1.65, margin: 0 }}>
              {a.how_it_works_today || "—"}
            </p>
          </div>
          <div style={{
            background: "oklch(0.96 0.022 155)", borderRadius: 12,
            padding: "16px 18px", border: "1px solid oklch(0.88 0.028 155)",
          }}>
            <div style={{
              fontSize: 11, fontWeight: 700, color: "oklch(0.46 0.085 150)",
              textTransform: "uppercase", letterSpacing: "0.07em",
              marginBottom: 8, fontFamily: "var(--font-mono)",
            }}>
              What changes with digital
            </div>
            <p style={{ fontSize: 14, color: "var(--ink-2)", lineHeight: 1.65, margin: 0 }}>
              {a.what_changes_with_digital || "—"}
            </p>
          </div>
        </div>
      </div>

      {/* source */}
      {concept.source_url && (
        <div style={{
          display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap",
          padding: "14px 18px", background: "var(--surface-2)",
          borderRadius: 10, border: "1px solid var(--hairline)",
        }}>
          <span style={{ fontSize: 12, color: "var(--ink-4)" }}>Source:</span>
          <a
            href={concept.source_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ fontSize: 13, fontWeight: 600, color: "var(--accent-ink)", textDecoration: "underline" }}
          >
            {concept.source_title || concept.source_url}
          </a>
          {concept.added_at && (
            <span style={{ fontSize: 11.5, color: "var(--ink-4)", marginLeft: "auto" }}>
              Added {(concept.added_at || "").slice(0, 10)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Main screen ──────────────────────────────────────────── */

function LearnScreen() {
  const concepts = window.KAIRO?.concepts || [];
  const groups   = window.KAIRO?.concept_groups || [];

  const [expandedSlug, setExpandedSlug] = useState(null);
  const [detailConcept, setDetailConcept] = useState(null);
  const [search, setSearch] = useState("");

  // ALL hooks must be called unconditionally before any early returns
  const filtered = useMemo(() => {
    if (!search.trim()) return concepts;
    const q = search.toLowerCase();
    return concepts.filter(c =>
      (c.concept_name  || "").toLowerCase().includes(q) ||
      (c.plain_english || "").toLowerCase().includes(q) ||
      (c.key_takeaway  || "").toLowerCase().includes(q)
    );
  }, [concepts, search]);

  const { rows, ungrouped } = useMemo(
    () => buildDisplayRows(concepts, groups),
    [concepts, groups]
  );

  function handleToggle(slug) {
    setExpandedSlug(prev => (prev === slug ? null : slug));
  }

  function handleDetail(concept) {
    setDetailConcept(concept);
    setExpandedSlug(null);
  }

  // ── Detail view (after all hooks) ──────────────────────────
  if (detailConcept) {
    return <ConceptDetail concept={detailConcept} onBack={() => setDetailConcept(null)} />;
  }

  const isSearching = search.trim().length > 0;

  // ── Empty state ─────────────────────────────────────────────
  if (concepts.length === 0) {
    return (
      <div className="screen-enter">
        <div style={{ marginBottom: 28 }}>
          <div className="eyebrow" style={{ marginBottom: 6 }}>Education</div>
          <h1 style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-0.025em", marginBottom: 8 }}>
            Crypto 101
          </h1>
          <p style={{ fontSize: 14.5, color: "var(--ink-3)", lineHeight: 1.65 }}>
            Digital currency concepts explained simply — real definitions, plain English,
            and comparisons to the financial world you already know.
          </p>
        </div>
        <div className="card" style={{ padding: "48px 36px", textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>📚</div>
          <div style={{ fontSize: 17, fontWeight: 700, color: "var(--ink)", marginBottom: 10 }}>
            No concepts yet
          </div>
          <p style={{ fontSize: 14, color: "var(--ink-3)", maxWidth: 400, margin: "0 auto", lineHeight: 1.65 }}>
            An admin can add concepts from the Admin panel by pasting a link to any
            official or government page — Kairo will auto-discover and explain all
            the concepts it finds.
          </p>
          <div style={{
            marginTop: 22, padding: "14px 18px",
            background: "var(--surface-2)", borderRadius: 10,
            fontSize: 12.5, color: "var(--ink-3)",
            border: "1px solid var(--hairline)", display: "inline-block", textAlign: "left",
          }}>
            <strong style={{ color: "var(--ink-2)" }}>Example URL:</strong><br />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 11.5 }}>
              https://www.scs.org.sg/articles/cryptocurrency-singapore
            </span>
          </div>
        </div>
      </div>
    );
  }

  // ── Main grid view ──────────────────────────────────────────
  return (
    <div className="screen-enter">
      {/* header */}
      <div style={{ marginBottom: 28 }}>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Education</div>
        <h1 style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-0.025em", marginBottom: 8 }}>
          Crypto 101
        </h1>
        <p style={{ fontSize: 14, color: "var(--ink-3)", lineHeight: 1.6 }}>
          Click any tile to preview — then "Full explanation" for the complete breakdown.
        </p>
      </div>

      {/* search */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 28, flexWrap: "wrap" }}>
        <input
          type="text"
          placeholder="Search concepts…"
          value={search}
          onChange={e => { setSearch(e.target.value); setExpandedSlug(null); }}
          style={{
            padding: "9px 16px", borderRadius: 9, fontSize: 14,
            border: "1px solid var(--hairline-strong)", background: "var(--surface)",
            color: "var(--ink)", outline: "none", minWidth: 220,
            fontFamily: "var(--font-sans)",
          }}
        />
        <span style={{ fontSize: 12.5, color: "var(--ink-4)" }}>
          {isSearching ? filtered.length + " of " : ""}{concepts.length} concept{concepts.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* search results — flat grid */}
      {isSearching ? (
        filtered.length === 0 ? (
          <div className="card" style={{ padding: "28px 24px", textAlign: "center" }}>
            <p style={{ color: "var(--ink-3)", fontSize: 14 }}>No concepts match your search.</p>
          </div>
        ) : (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
            gap: 12,
          }}>
            {filtered.map(c => (
              <ConceptTile
                key={c.concept_slug}
                concept={c}
                size="sm"
                isExpanded={expandedSlug === c.concept_slug}
                onToggle={handleToggle}
                onDetail={handleDetail}
              />
            ))}
          </div>
        )
      ) : (
        <>
          {/* grouped rows */}
          {rows.map(({ anchor, related }) => (
            <GroupRow
              key={anchor.concept_slug}
              anchor={anchor}
              related={related}
              expandedSlug={expandedSlug}
              onToggle={handleToggle}
              onDetail={handleDetail}
            />
          ))}

          {/* ungrouped */}
          {ungrouped.length > 0 && (
            <>
              {rows.length > 0 && (
                <div style={{
                  fontSize: 11, fontWeight: 700, letterSpacing: "0.08em",
                  textTransform: "uppercase", color: "var(--ink-4)",
                  marginTop: 8, marginBottom: 12, fontFamily: "var(--font-mono)",
                }}>
                  More concepts
                </div>
              )}
              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
                gap: 12,
              }}>
                {ungrouped.map(c => (
                  <ConceptTile
                    key={c.concept_slug}
                    concept={c}
                    size="sm"
                    isExpanded={expandedSlug === c.concept_slug}
                    onToggle={handleToggle}
                    onDetail={handleDetail}
                  />
                ))}
              </div>
            </>
          )}
        </>
      )}

      {/* footer */}
      <div style={{
        marginTop: 36, padding: "14px 18px",
        background: "var(--surface-2)", borderRadius: 10, border: "1px solid var(--hairline)",
      }}>
        <p style={{ fontSize: 12, color: "var(--ink-3)", margin: 0, lineHeight: 1.6 }}>
          <strong style={{ color: "var(--ink-2)" }}>Powered by Gemini</strong> — concepts are
          auto-extracted from official sources and explained at three levels: technical definition,
          plain English, and a real-world analogy. Admins can add new sources from the Admin panel.
        </p>
      </div>
    </div>
  );
}

window.LearnScreen = LearnScreen;
