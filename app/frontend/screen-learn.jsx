/* ============================================================
   Kairo — Crypto 101 screen
   Plain-English explainers for digital currency concepts.
   ============================================================ */
const { useState, useMemo } = React;

/* ── Add concept form ─────────────────────────────────────── */

function AddConceptForm({ onSubmit }) {
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [open, setOpen] = useState(false);

  function handleSubmit(e) {
    e.preventDefault();
    if (!url.trim() || !name.trim()) return;
    onSubmit(url.trim(), name.trim());
  }

  return (
    <div style={{ marginBottom: 32 }}>
      <button
        onClick={() => setOpen(x => !x)}
        style={{
          display: "inline-flex", alignItems: "center", gap: 8,
          padding: "10px 20px", borderRadius: 10,
          background: open ? "var(--surface-2)" : "var(--accent)",
          color: open ? "var(--ink-3)" : "var(--paper)",
          border: open ? "1px solid var(--hairline)" : "none",
          fontSize: 14, fontWeight: 700, cursor: "pointer",
          transition: "all 0.15s",
        }}
      >
        <span style={{ fontSize: 16 }}>{open ? "✕" : "+"}</span>
        {open ? "Cancel" : "Explain a new concept"}
      </button>

      {open && (
        <form onSubmit={handleSubmit} style={{
          marginTop: 16, padding: "22px 24px",
          background: "var(--surface)", border: "1px solid var(--hairline)",
          borderRadius: 14, maxWidth: 600,
        }}>
          <div style={{ fontSize: 13, color: "var(--ink-3)", marginBottom: 16, lineHeight: 1.5 }}>
            Paste a link to any official or government page that explains a crypto concept —
            Kairo will translate it into plain English automatically.
          </div>

          <div style={{ marginBottom: 14 }}>
            <label style={{ display: "block", fontSize: 12.5, fontWeight: 700, color: "var(--ink-2)", marginBottom: 5 }}>
              Source URL
            </label>
            <input
              type="url"
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="https://www.mas.gov.sg/digital-assets/…"
              required
              style={{
                width: "100%", padding: "10px 14px", borderRadius: 8,
                border: "1px solid var(--hairline-strong)",
                background: "var(--surface)", color: "var(--ink)",
                fontSize: 14, fontFamily: "var(--font-sans)", boxSizing: "border-box",
                outline: "none",
              }}
            />
          </div>

          <div style={{ marginBottom: 18 }}>
            <label style={{ display: "block", fontSize: 12.5, fontWeight: 700, color: "var(--ink-2)", marginBottom: 5 }}>
              Concept name
            </label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Blockchain, Cryptocurrency, Digital Wallet"
              required
              style={{
                width: "100%", padding: "10px 14px", borderRadius: 8,
                border: "1px solid var(--hairline-strong)",
                background: "var(--surface)", color: "var(--ink)",
                fontSize: 14, fontFamily: "var(--font-sans)", boxSizing: "border-box",
                outline: "none",
              }}
            />
          </div>

          <button
            type="submit"
            style={{
              padding: "11px 24px", borderRadius: 8,
              background: "var(--accent)", color: "var(--paper)",
              border: "none", fontSize: 14.5, fontWeight: 700,
              cursor: "pointer", transition: "background 0.15s",
            }}
          >
            Generate explanation →
          </button>
          <div style={{ fontSize: 11.5, color: "var(--ink-4)", marginTop: 10 }}>
            The page will reload briefly while Kairo fetches and explains the concept.
          </div>
        </form>
      )}
    </div>
  );
}

/* ── Concept card ─────────────────────────────────────────── */

function ConceptCard({ concept }) {
  const [expanded, setExpanded] = useState(false);
  const analogy = concept.traditional_analogy || {};

  return (
    <div className="card" style={{ padding: "24px 26px", marginBottom: 18 }}>
      {/* header */}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 14, marginBottom: 16 }}>
        <span style={{ fontSize: 32, flexShrink: 0, lineHeight: 1 }}>
          {concept.emoji || "🔗"}
        </span>
        <div style={{ flex: 1 }}>
          <h2 style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.02em", marginBottom: 4 }}>
            {concept.concept_name}
          </h2>
          {concept.key_takeaway && (
            <div style={{ fontSize: 13.5, color: "var(--accent-ink)", fontWeight: 600 }}>
              {concept.key_takeaway}
            </div>
          )}
        </div>
      </div>

      {/* real description */}
      <div style={{ marginBottom: 16 }}>
        <div style={{
          fontSize: 10.5, fontWeight: 700, letterSpacing: "0.10em",
          textTransform: "uppercase", color: "var(--ink-3)", marginBottom: 6,
          fontFamily: "var(--font-mono)",
        }}>
          Official Definition
        </div>
        <p style={{ fontSize: 14, color: "var(--ink-2)", lineHeight: 1.65 }}>
          {concept.real_description}
        </p>
      </div>

      {/* plain english */}
      <div style={{
        background: "var(--accent-soft)", borderRadius: 12,
        padding: "16px 18px", marginBottom: 16,
        border: "1px solid color-mix(in oklch, var(--accent) 20%, transparent)",
      }}>
        <div style={{
          fontSize: 10.5, fontWeight: 700, letterSpacing: "0.10em",
          textTransform: "uppercase", color: "var(--accent-ink)", marginBottom: 6,
          fontFamily: "var(--font-mono)",
        }}>
          In Plain English
        </div>
        <p style={{ fontSize: 15, color: "var(--ink)", lineHeight: 1.65, fontWeight: 500 }}>
          {concept.plain_english}
        </p>
      </div>

      {/* expand button */}
      <button
        onClick={() => setExpanded(x => !x)}
        style={{
          fontSize: 12.5, fontWeight: 600, color: "var(--accent-ink)",
          cursor: "pointer", background: "none", border: "none", padding: 0,
          display: "inline-flex", alignItems: "center", gap: 4,
        }}
      >
        <span style={{
          display: "inline-block",
          transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
          transition: "transform 0.2s",
        }}>▾</span>
        {expanded ? "Hide analogy" : "See real-world analogy"}
      </button>

      {expanded && (
        <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--hairline)" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
            {/* how today */}
            <div style={{
              background: "var(--surface-2)", borderRadius: 10, padding: "16px 18px",
              border: "1px solid var(--hairline)",
            }}>
              <div style={{
                fontSize: 10.5, fontWeight: 700, letterSpacing: "0.08em",
                textTransform: "uppercase", color: "var(--ink-3)", marginBottom: 8,
                fontFamily: "var(--font-mono)",
              }}>
                How it works today
              </div>
              <p style={{ fontSize: 13.5, color: "var(--ink-2)", lineHeight: 1.6 }}>
                {analogy.how_it_works_today || "—"}
              </p>
            </div>

            {/* what changes */}
            <div style={{
              background: "oklch(0.96 0.022 155)", borderRadius: 10, padding: "16px 18px",
              border: "1px solid oklch(0.88 0.030 155)",
            }}>
              <div style={{
                fontSize: 10.5, fontWeight: 700, letterSpacing: "0.08em",
                textTransform: "uppercase", color: "oklch(0.46 0.085 150)", marginBottom: 8,
                fontFamily: "var(--font-mono)",
              }}>
                What changes with digital
              </div>
              <p style={{ fontSize: 13.5, color: "var(--ink-2)", lineHeight: 1.6 }}>
                {analogy.what_changes_with_digital || "—"}
              </p>
            </div>
          </div>

          {/* source */}
          {concept.source_url && (
            <div style={{ marginTop: 14, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 11.5, color: "var(--ink-4)" }}>Source:</span>
              <a
                href={concept.source_url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ fontSize: 12, fontWeight: 600, color: "var(--accent-ink)", textDecoration: "underline" }}
              >
                {concept.source_title || concept.source_url}
              </a>
              {concept.added_at && (
                <span style={{ fontSize: 11, color: "var(--ink-4)", marginLeft: "auto" }}>
                  Added {concept.added_at.slice(0, 10)}
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Main screen ──────────────────────────────────────────── */

function LearnScreen() {
  const concepts = window.KAIRO?.concepts || [];
  const [search, setSearch] = useState("");

  function handleAddConcept(url, name) {
    try {
      const parentUrl = new URL(window.top.location.href);
      parentUrl.searchParams.set("kairo_action", "add-concept");
      parentUrl.searchParams.set("concept_url", url);
      parentUrl.searchParams.set("concept_name", name);
      window.top.location.href = parentUrl.toString();
    } catch (_) {
      const thisUrl = new URL(window.location.href);
      thisUrl.searchParams.set("kairo_action", "add-concept");
      thisUrl.searchParams.set("concept_url", url);
      thisUrl.searchParams.set("concept_name", name);
      window.location.href = thisUrl.toString();
    }
  }

  const filtered = useMemo(() => {
    if (!search.trim()) return concepts;
    const q = search.toLowerCase();
    return concepts.filter(c =>
      (c.concept_name || "").toLowerCase().includes(q) ||
      (c.plain_english || "").toLowerCase().includes(q) ||
      (c.key_takeaway || "").toLowerCase().includes(q)
    );
  }, [concepts, search]);

  return (
    <div className="screen-enter">
      {/* header */}
      <div style={{ marginBottom: 32 }}>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Education</div>
        <h1 style={{ fontSize: 30, fontWeight: 800, letterSpacing: "-0.025em", marginBottom: 8 }}>
          Crypto 101
        </h1>
        <p style={{ fontSize: 14.5, color: "var(--ink-3)", maxWidth: 560, lineHeight: 1.65 }}>
          Digital currency explained simply — real definitions, plain English, and a comparison
          to the traditional financial system you already know.
        </p>
      </div>

      {/* add concept form */}
      <AddConceptForm onSubmit={handleAddConcept} />

      {/* search (only when there are concepts) */}
      {concepts.length > 0 && (
        <div style={{ marginBottom: 24, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <input
            type="text"
            placeholder="Search concepts…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{
              padding: "9px 16px", borderRadius: 9, fontSize: 14,
              border: "1px solid var(--hairline-strong)", background: "var(--surface)",
              color: "var(--ink)", outline: "none", minWidth: 240,
              fontFamily: "var(--font-sans)",
            }}
          />
          <span style={{ fontSize: 12.5, color: "var(--ink-4)" }}>
            {filtered.length} concept{filtered.length !== 1 ? "s" : ""}
          </span>
        </div>
      )}

      {/* content */}
      {concepts.length === 0 ? (
        <div className="card" style={{ padding: "48px 36px", textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>📚</div>
          <div style={{ fontSize: 17, fontWeight: 700, color: "var(--ink)", marginBottom: 10 }}>
            No concepts explained yet
          </div>
          <p style={{ fontSize: 14, color: "var(--ink-3)", maxWidth: 380, margin: "0 auto", lineHeight: 1.65 }}>
            Use the form above to add any concept — paste a link to an official government
            or regulator page and Kairo will break it down for you.
          </p>
          <div style={{
            marginTop: 22, padding: "14px 18px", background: "var(--surface-2)",
            borderRadius: 10, fontSize: 12.5, color: "var(--ink-3)",
            border: "1px solid var(--hairline)", display: "inline-block", textAlign: "left",
          }}>
            <strong style={{ color: "var(--ink-2)" }}>Example:</strong><br />
            URL: <span style={{ fontFamily: "var(--font-mono)", fontSize: 11.5 }}>https://www.scs.org.sg/articles/cryptocurrency-singapore</span><br />
            Concept: <span style={{ fontWeight: 600 }}>Cryptocurrency</span>
          </div>
        </div>
      ) : filtered.length === 0 ? (
        <div className="card" style={{ padding: "28px 24px", textAlign: "center" }}>
          <p style={{ color: "var(--ink-3)", fontSize: 14 }}>No concepts match your search.</p>
        </div>
      ) : (
        filtered.map(c => <ConceptCard key={c.concept_slug || c.concept_name} concept={c} />)
      )}

      {/* footer */}
      <div style={{
        marginTop: 32, padding: "16px 20px",
        background: "var(--surface-2)", borderRadius: 12, border: "1px solid var(--hairline)",
      }}>
        <div style={{ fontSize: 12, color: "var(--ink-3)", lineHeight: 1.6 }}>
          <strong style={{ color: "var(--ink-2)" }}>How it works:</strong>{" "}
          Paste any link to a government or official regulator page, give it a concept name,
          and Kairo reads the page and asks Gemini to explain it at three levels —
          the official definition, plain English, and an analogy to the financial world you already know.
          Each concept is stored once.
        </div>
      </div>
    </div>
  );
}

window.LearnScreen = LearnScreen;
