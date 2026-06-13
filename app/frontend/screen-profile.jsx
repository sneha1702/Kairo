/* ============================================================
   Kairo — Profile screen (editable)
   ============================================================ */
const { useState } = React;

const PROFESSIONS = [
  "Software Engineer / Developer", "Data Scientist / Analyst",
  "Finance / Investment Professional", "Entrepreneur / Founder",
  "Student", "Product Manager", "Designer / Creative",
  "Researcher / Academic", "Marketing / Growth", "Other",
];
const TRADING_PROFILES = ["Beginner", "Experienced"];
const PURPOSES = [
  "Learn about crypto markets", "Track narratives & trends",
  "Research before investing", "Professional market intelligence",
  "Building a product or tool", "Academic or research purposes",
  "Just exploring",
];

function ProfileScreen() {
  const user = window.KAIRO?.auth_user || {};
  const filled = user.profile_filled || 0;
  const total  = user.profile_total  || 6;
  const pct    = total > 0 ? Math.round((filled / total) * 100) : 0;
  const isComplete = filled >= total;

  const [firstName,      setFirstName]      = useState(user.first_name      || "");
  const [lastName,       setLastName]       = useState(user.last_name       || "");
  const [email,          setEmail]          = useState(user.email           || "");
  const [profession,     setProfession]     = useState(user.profession      || "");
  const [tradingProfile, setTradingProfile] = useState(user.trading_profile || "");
  const [purpose,        setPurpose]        = useState(user.purpose         || "");
  const [saving,         setSaving]         = useState(false);

  const initials = (() => {
    const f = (user.first_name || "").trim();
    const l = (user.last_name  || "").trim();
    if (f && l) return (f[0] + l[0]).toUpperCase();
    if (f) return f.slice(0, 2).toUpperCase();
    return (user.username || "?").slice(0, 2).toUpperCase();
  })();

  const displayName = [user.first_name, user.last_name].filter(Boolean).join(" ")
    || user.username || "You";

  const ACCENT_COLORS = [
    "oklch(0.64 0.124 42)", "oklch(0.61 0.072 150)",
    "oklch(0.59 0.090 252)", "oklch(0.62 0.090 300)",
  ];
  const avatarBg = ACCENT_COLORS[(user.username || "").charCodeAt(0) % ACCENT_COLORS.length] || "var(--accent)";

  function handleSave() {
    setSaving(true);
    const data = JSON.stringify({
      first_name:      firstName.trim(),
      last_name:       lastName.trim(),
      email:           email.trim(),
      profession:      profession,
      trading_profile: tradingProfile,
      purpose:         purpose,
    });
    try {
      const url = new URL(window.top.location.href);
      url.searchParams.set("kairo_action", "save-profile");
      url.searchParams.set("profile_data", data);
      window.top.location.href = url.toString();
    } catch (_) {
      try {
        const url = new URL(window.location.href);
        url.searchParams.set("kairo_action", "save-profile");
        url.searchParams.set("profile_data", data);
        window.location.href = url.toString();
      } catch (__) { setSaving(false); }
    }
  }

  const inputStyle = {
    width: "100%", padding: "9px 13px",
    background: "var(--surface-2)", border: "1px solid var(--hairline-strong)",
    borderRadius: "var(--r-sm)", color: "var(--ink)", fontSize: 14.5,
    fontFamily: "var(--font-sans)", outline: "none",
    transition: "border-color 0.15s", boxSizing: "border-box",
  };
  const labelStyle = {
    fontSize: 12.5, color: "var(--ink-3)", fontWeight: 600,
    letterSpacing: "0.01em", marginBottom: 5, display: "block",
  };

  function focusIn(e)  { e.target.style.borderColor = "var(--accent)"; }
  function focusOut(e) { e.target.style.borderColor = "var(--hairline-strong)"; }

  return (
    <div className="screen-enter">
      <div style={{ maxWidth: 600, margin: "0 auto" }}>

        {/* ── Header ── */}
        <div style={{ display: "flex", alignItems: "center", gap: 20, marginBottom: 32 }}>
          <div style={{
            width: 72, height: 72, borderRadius: "50%",
            background: avatarBg, color: "oklch(0.98 0.004 80)",
            display: "grid", placeItems: "center",
            fontSize: 27, fontWeight: 800, flexShrink: 0, letterSpacing: "-0.02em",
          }}>{initials}</div>
          <div>
            <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em" }}>
              {displayName}
            </h2>
            <div style={{ fontSize: 13, color: "var(--ink-3)", marginTop: 4, display: "flex", gap: 8, alignItems: "center" }}>
              <span>@{user.username}</span>
              <span style={{
                background: user.role === "admin" ? "var(--accent)" : "var(--ink-3)",
                color: "var(--paper)", fontSize: 9, fontWeight: 700,
                letterSpacing: "0.08em", textTransform: "uppercase",
                padding: "2px 7px", borderRadius: 99,
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
            <div style={{ fontWeight: 700, color: "var(--accent-ink)", fontSize: 15, marginBottom: 6, display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 18 }}>✦</span>
              Complete your profile — get 1 month of free Plus
            </div>
            <div style={{ fontSize: 13, color: "var(--ink-2)", marginBottom: 14 }}>
              {filled} of {total} details filled in. Fill all fields below and save.
            </div>
            <div style={{ height: 7, background: "var(--hairline)", borderRadius: 99, overflow: "hidden" }}>
              <div style={{
                height: "100%", width: `${pct}%`, background: "var(--accent)",
                borderRadius: 99, transition: "width 0.5s cubic-bezier(0.22,1,0.36,1)",
              }} />
            </div>
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

        {/* ── Editable profile form ── */}
        <div className="card" style={{ padding: "var(--card-pad)", marginBottom: 20 }}>
          <div className="eyebrow" style={{ marginBottom: 20 }}>Your details</div>

          {/* Name row */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
            <div>
              <label style={labelStyle}>First name</label>
              <input
                style={inputStyle} type="text" value={firstName} placeholder="Jane"
                onChange={e => setFirstName(e.target.value)}
                onFocus={focusIn} onBlur={focusOut}
              />
            </div>
            <div>
              <label style={labelStyle}>Last name</label>
              <input
                style={inputStyle} type="text" value={lastName} placeholder="Smith"
                onChange={e => setLastName(e.target.value)}
                onFocus={focusIn} onBlur={focusOut}
              />
            </div>
          </div>

          {/* Email */}
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Email</label>
            <input
              style={inputStyle} type="email" value={email} placeholder="you@example.com"
              onChange={e => setEmail(e.target.value)}
              onFocus={focusIn} onBlur={focusOut}
            />
          </div>

          {/* Profession */}
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Profession</label>
            <select
              style={{ ...inputStyle, cursor: "pointer", appearance: "auto" }}
              value={profession}
              onChange={e => setProfession(e.target.value)}
              onFocus={focusIn} onBlur={focusOut}
            >
              <option value="">Select your profession…</option>
              {PROFESSIONS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>

          {/* Trading experience */}
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Trading experience</label>
            <select
              style={{ ...inputStyle, cursor: "pointer", appearance: "auto" }}
              value={tradingProfile}
              onChange={e => setTradingProfile(e.target.value)}
              onFocus={focusIn} onBlur={focusOut}
            >
              <option value="">Select your experience level…</option>
              {TRADING_PROFILES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          {/* Purpose */}
          <div style={{ marginBottom: 24 }}>
            <label style={labelStyle}>Why did you subscribe?</label>
            <select
              style={{ ...inputStyle, cursor: "pointer", appearance: "auto" }}
              value={purpose}
              onChange={e => setPurpose(e.target.value)}
              onFocus={focusIn} onBlur={focusOut}
            >
              <option value="">Select your purpose…</option>
              {PURPOSES.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>

          {/* Save button */}
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              width: "100%", padding: "12px 24px",
              background: saving ? "var(--ink-4)" : "var(--accent)",
              color: "var(--paper)", border: "none",
              borderRadius: "var(--r-sm)", fontSize: 15, fontWeight: 700,
              cursor: saving ? "default" : "pointer",
              fontFamily: "var(--font-sans)", transition: "background 0.15s",
            }}
            onMouseOver={e => { if (!saving) e.currentTarget.style.background = "var(--accent-ink)"; }}
            onMouseOut={e => { if (!saving) e.currentTarget.style.background = "var(--accent)"; }}
          >
            {saving ? "Saving…" : "Save Profile"}
          </button>
        </div>

      </div>
    </div>
  );
}

window.ProfileScreen = ProfileScreen;
