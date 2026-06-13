/* ============================================================
   Kairo — Profile screen (read-only display, edit via Profile tab)
   ============================================================ */
const { useState } = React;

function ProfileScreen() {
  const user = window.KAIRO?.auth_user || {};
  const filled = user.profile_filled || 0;
  const total  = user.profile_total  || 6;
  const pct    = total > 0 ? Math.round((filled / total) * 100) : 0;
  const isComplete = filled >= total;

  const initials = (() => {
    const f = (user.first_name || "").trim();
    const l = (user.last_name  || "").trim();
    if (f && l) return (f[0] + l[0]).toUpperCase();
    if (f) return f.slice(0, 2).toUpperCase();
    return (user.username || "?").slice(0, 2).toUpperCase();
  })();

  const displayName = [user.first_name, user.last_name].filter(Boolean).join(" ")
    || user.username || "You";

  function handleSignOut(e) {
    e.preventDefault();
    try {
      window.parent.postMessage({ type: "kairo-action", action: "logout" }, "*");
    } catch (_) {
      try {
        const url = new URL(window.top.location.href);
        url.searchParams.set("kairo_action", "logout");
        window.top.location.href = url.toString();
      } catch (__) {}
    }
  }

  const profileFields = [
    { label: "First name",         value: user.first_name },
    { label: "Last name",          value: user.last_name },
    { label: "Email",              value: user.email },
    { label: "Profession",         value: user.profession },
    { label: "Trading experience", value: user.trading_profile },
    { label: "Purpose",            value: user.purpose },
  ];

  const ACCENT_COLORS = [
    "oklch(0.64 0.124 42)",
    "oklch(0.61 0.072 150)",
    "oklch(0.59 0.090 252)",
    "oklch(0.62 0.090 300)",
  ];
  const avatarBg = ACCENT_COLORS[
    (user.username || "").charCodeAt(0) % ACCENT_COLORS.length
  ] || "var(--accent)";

  return (
    <div className="screen-enter">
      <div style={{ maxWidth: 600, margin: "0 auto" }}>

        {/* ── Header ── */}
        <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 32 }}>
          <div style={{
            width: 72, height: 72, borderRadius: "50%",
            background: avatarBg, color: "oklch(0.98 0.004 80)",
            display: "grid", placeItems: "center",
            fontSize: 27, fontWeight: 800, flexShrink: 0,
            letterSpacing: "-0.02em",
          }}>{initials}</div>
          <div>
            <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em" }}>
              {displayName}
            </h2>
            <div style={{ fontSize: 13, color: "var(--ink-3)", marginTop: 4, display: "flex", gap: 8, alignItems: "center" }}>
              <span>@{user.username}</span>
              <span style={{
                background: user.role === "admin" ? "var(--accent)" : "var(--ink-3)",
                color: "var(--paper)",
                fontSize: 9, fontWeight: 700, letterSpacing: "0.08em",
                textTransform: "uppercase", padding: "2px 7px", borderRadius: 99,
              }}>{user.role}</span>
            </div>
          </div>
        </div>

        {/* ── Plus membership CTA ── */}
        {!isComplete ? (
          <div style={{
            background: "var(--accent-soft)",
            border: "1.5px solid color-mix(in oklch, var(--accent) 40%, transparent)",
            borderRadius: "var(--r-lg)", padding: "20px 24px", marginBottom: 28,
          }}>
            <div style={{
              fontWeight: 700, color: "var(--accent-ink)", fontSize: 15, marginBottom: 6,
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <span style={{ fontSize: 18 }}>✦</span>
              Complete your profile — get 1 month of free Plus
            </div>
            <div style={{ fontSize: 13, color: "var(--ink-2)", marginBottom: 14 }}>
              {filled} of {total} details filled in.
            </div>
            {/* Progress track */}
            <div style={{ height: 7, background: "var(--hairline)", borderRadius: 99, overflow: "hidden", marginBottom: 10 }}>
              <div style={{
                height: "100%", width: `${pct}%`,
                background: "var(--accent)", borderRadius: 99,
                transition: "width 0.5s cubic-bezier(0.22,1,0.36,1)",
              }} />
            </div>
            <p style={{ fontSize: 12.5, color: "var(--ink-3)", margin: 0 }}>
              Open the <strong>Profile</strong> tab above to fill in the remaining {total - filled} field{total - filled !== 1 ? "s" : ""}.
            </p>
          </div>
        ) : (
          <div style={{
            background: "oklch(0.96 0.025 155)", border: "1.5px solid var(--pos)",
            borderRadius: "var(--r-lg)", padding: "18px 22px", marginBottom: 28,
          }}>
            <div style={{ fontWeight: 700, color: "var(--pos)", fontSize: 15 }}>
              🎉 Profile complete — your free Plus month is active!
            </div>
          </div>
        )}

        {/* ── Profile fields card ── */}
        <div className="card" style={{ padding: "var(--card-pad)", marginBottom: 20 }}>
          <div className="eyebrow" style={{ marginBottom: 18 }}>Your details</div>
          <div style={{ display: "grid", gap: 16 }}>
            {profileFields.map(f => (
              <div key={f.label} style={{
                display: "grid",
                gridTemplateColumns: "150px 1fr",
                gap: 12, alignItems: "start",
              }}>
                <div style={{
                  fontSize: 12.5, color: "var(--ink-3)", fontWeight: 600,
                  paddingTop: 1, letterSpacing: "0.01em",
                }}>{f.label}</div>
                <div style={{
                  fontSize: 14.5,
                  color: f.value ? "var(--ink)" : "var(--ink-4)",
                  fontStyle: f.value ? "normal" : "italic",
                }}>{f.value || "not set"}</div>
              </div>
            ))}
          </div>
          <div style={{
            marginTop: 20, paddingTop: 16,
            borderTop: "1px solid var(--hairline)",
          }}>
            <p style={{ fontSize: 12.5, color: "var(--ink-3)", margin: 0 }}>
              To edit these details or change your password, open the{" "}
              <strong style={{ color: "var(--ink-2)" }}>Profile</strong> tab in the navigation bar above.
            </p>
          </div>
        </div>

        {/* ── Sign out ── */}
        <button
          onClick={handleSignOut}
          style={{
            width: "100%", padding: "13px 24px",
            background: "var(--surface)",
            border: "1px solid var(--hairline-strong)",
            borderRadius: "var(--r-sm)", color: "var(--ink-2)",
            fontFamily: "var(--font-sans)", fontSize: 15, fontWeight: 600,
            cursor: "pointer", transition: "background 0.15s, color 0.15s",
          }}
          onMouseOver={e => { e.currentTarget.style.background = "var(--surface-2)"; e.currentTarget.style.color = "var(--ink)"; }}
          onMouseOut={e => { e.currentTarget.style.background = "var(--surface)"; e.currentTarget.style.color = "var(--ink-2)"; }}
        >
          Sign out
        </button>

      </div>
    </div>
  );
}

window.ProfileScreen = ProfileScreen;
