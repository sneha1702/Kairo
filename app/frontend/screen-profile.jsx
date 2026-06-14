/* ============================================================
   Kairo — Profile screen (editable)
   ============================================================ */
const { useState, useEffect } = React;

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

function Toast({ message, type = "success" }) {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const t = setTimeout(() => setVisible(false), 5000);
    return () => clearTimeout(t);
  }, []);
  if (!visible) return null;
  const isErr = type === "error";
  return (
    <div style={{
      position: "fixed", top: 24, right: 24, zIndex: 9999,
      background: isErr ? "oklch(0.93 0.04 22)" : "oklch(0.96 0.025 155)",
      border: `1.5px solid ${isErr ? "oklch(0.70 0.09 22)" : "var(--pos)"}`,
      color: isErr ? "oklch(0.52 0.115 22)" : "var(--pos)",
      borderRadius: "var(--r-md)", padding: "14px 20px",
      fontWeight: 600, fontSize: 14,
      boxShadow: "0 4px 24px oklch(0.5 0.02 60 / 0.12)",
    }}>
      {message}
    </div>
  );
}

function ProfileScreen() {
  const K = window.KAIRO;
  const user = K?.auth_user || {};
  const config = K?.config || {};

  const filled = user.profile_filled || 0;
  const total  = user.profile_total  || 6;
  const pct    = total > 0 ? Math.round((filled / total) * 100) : 0;
  const isComplete = filled >= total;

  /* ── profile form ── */
  const [firstName,      setFirstName]      = useState(user.first_name      || "");
  const [lastName,       setLastName]       = useState(user.last_name       || "");
  const [email,          setEmail]          = useState(user.email           || "");
  const [profession,     setProfession]     = useState(user.profession      || "");
  const [tradingProfile, setTradingProfile] = useState(user.trading_profile || "");
  const [purpose,        setPurpose]        = useState(user.purpose         || "");
  const [saving,         setSaving]         = useState(false);
  // Stay in edit mode if returning from a save (config.toast is set by the server)
  const [editing,        setEditing]        = useState(!!config.toast);

  /* ── change password ── */
  const [oldPw,    setOldPw]    = useState("");
  const [newPw1,   setNewPw1]   = useState("");
  const [newPw2,   setNewPw2]   = useState("");
  const [pwSaving, setPwSaving] = useState(false);
  const [pwError,  setPwError]  = useState("");

  /* ── delete account ── */
  const [showDelete,     setShowDelete]     = useState(false);
  const [deleteConfirm,  setDeleteConfirm]  = useState("");
  const [deleting,       setDeleting]       = useState(false);

  /* ── server-sent one-time signals ── */
  const [toast,     setToast]     = useState(config.toast       || null);
  const [pwResult,  setPwResult]  = useState(config.pw_result   || null);
  const pwMessage = config.pw_message || "";

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

  function navigate(params) {
    try {
      const url = new URL(window.top.location.href);
      Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
      window.top.location.href = url.toString();
    } catch (_) {
      try {
        const url = new URL(window.location.href);
        Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
        window.location.href = url.toString();
      } catch (__) {}
    }
  }

  function handleSave() {
    setSaving(true);
    navigate({
      kairo_action:  "save-profile",
      profile_data:  JSON.stringify({
        first_name:      firstName.trim(),
        last_name:       lastName.trim(),
        email:           email.trim(),
        profession,
        trading_profile: tradingProfile,
        purpose,
      }),
    });
  }

  function handleCancel() {
    const u = window.KAIRO?.auth_user || {};
    setFirstName(u.first_name || "");
    setLastName(u.last_name || "");
    setEmail(u.email || "");
    setProfession(u.profession || "");
    setTradingProfile(u.trading_profile || "");
    setPurpose(u.purpose || "");
    setEditing(false);
  }

  function handleChangePassword() {
    setPwError("");
    if (!oldPw || !newPw1)   { setPwError("Please fill in all password fields."); return; }
    if (newPw1.length < 10)  { setPwError("New password must be at least 10 characters."); return; }
    if (!/[A-Za-z]/.test(newPw1) || !/\d/.test(newPw1)) {
      setPwError("Use a mix of letters and numbers."); return;
    }
    if (newPw1 === oldPw)    { setPwError("Pick a new password — don't reuse the old one."); return; }
    if (newPw1 !== newPw2)   { setPwError("Passwords do not match."); return; }
    setPwSaving(true);
    navigate({
      kairo_action: "change-password",
      pw_data:      JSON.stringify({ old: oldPw, new: newPw1 }),
    });
  }

  function handleDeleteAccount() {
    if (deleteConfirm !== user.username) return;
    setDeleting(true);
    navigate({
      kairo_action: "delete-account",
      confirm_user: user.username,
    });
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

  const disabledInputStyle = {
    ...inputStyle,
    background: "var(--hairline)",
    color: "var(--ink-3)",
    cursor: "not-allowed",
    opacity: 0.65,
  };

  /* pw result toast text */
  const pwResultToast = pwResult === "ok"
    ? { msg: "Password changed. You've been kept signed in on this device; sign in again on any others.", type: "success" }
    : pwResult === "wrong_password"
    ? { msg: "Current password is incorrect.", type: "error" }
    : pwResult === "weak_password"
    ? { msg: pwMessage || "Choose a stronger password.", type: "error" }
    : pwResult === "error"
    ? { msg: "Password change failed. Try again.", type: "error" }
    : null;

  return (
    <div className="screen-enter">
      {toast       && <Toast key="profile-toast"   message={toast}            type="success" />}
      {pwResultToast && <Toast key="pw-toast" message={pwResultToast.msg} type={pwResultToast.type} />}

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

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
            <div>
              <label style={labelStyle}>First name</label>
              <input style={editing ? inputStyle : disabledInputStyle} type="text" value={firstName} placeholder="Jane"
                onChange={e => setFirstName(e.target.value)} onFocus={focusIn} onBlur={focusOut} disabled={!editing} />
            </div>
            <div>
              <label style={labelStyle}>Last name</label>
              <input style={editing ? inputStyle : disabledInputStyle} type="text" value={lastName} placeholder="Smith"
                onChange={e => setLastName(e.target.value)} onFocus={focusIn} onBlur={focusOut} disabled={!editing} />
            </div>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Email</label>
            <input style={editing ? inputStyle : disabledInputStyle} type="email" value={email} placeholder="you@example.com"
              onChange={e => setEmail(e.target.value)} onFocus={focusIn} onBlur={focusOut} disabled={!editing} />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Profession</label>
            <select style={editing ? { ...inputStyle, cursor: "pointer", appearance: "auto" } : { ...disabledInputStyle, appearance: "auto" }}
              value={profession} onChange={e => setProfession(e.target.value)} onFocus={focusIn} onBlur={focusOut} disabled={!editing}>
              <option value="">Select your profession…</option>
              {PROFESSIONS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Trading experience</label>
            <select style={editing ? { ...inputStyle, cursor: "pointer", appearance: "auto" } : { ...disabledInputStyle, appearance: "auto" }}
              value={tradingProfile} onChange={e => setTradingProfile(e.target.value)} onFocus={focusIn} onBlur={focusOut} disabled={!editing}>
              <option value="">Select your experience level…</option>
              {TRADING_PROFILES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={labelStyle}>Why did you subscribe?</label>
            <select style={editing ? { ...inputStyle, cursor: "pointer", appearance: "auto" } : { ...disabledInputStyle, appearance: "auto" }}
              value={purpose} onChange={e => setPurpose(e.target.value)} onFocus={focusIn} onBlur={focusOut} disabled={!editing}>
              <option value="">Select your purpose…</option>
              {PURPOSES.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>

          {!editing ? (
            <button onClick={() => setEditing(true)} style={{
              width: "100%", padding: "12px 24px",
              background: "var(--surface-2)", color: "var(--ink-2)",
              border: "1px solid var(--hairline-strong)",
              borderRadius: "var(--r-sm)", fontSize: 15, fontWeight: 700,
              cursor: "pointer", fontFamily: "var(--font-sans)", transition: "all 0.15s",
            }}
            onMouseOver={e => { e.currentTarget.style.background = "var(--surface)"; e.currentTarget.style.borderColor = "var(--ink-3)"; }}
            onMouseOut={e => { e.currentTarget.style.background = "var(--surface-2)"; e.currentTarget.style.borderColor = "var(--hairline-strong)"; }}>
              Edit Profile
            </button>
          ) : (
            <div style={{ display: "flex", gap: 10 }}>
              <button onClick={handleSave} disabled={saving} style={{
                flex: 1, padding: "12px 24px",
                background: saving ? "var(--ink-4)" : "var(--accent)",
                color: "var(--paper)", border: "none",
                borderRadius: "var(--r-sm)", fontSize: 15, fontWeight: 700,
                cursor: saving ? "default" : "pointer",
                fontFamily: "var(--font-sans)", transition: "background 0.15s",
              }}
              onMouseOver={e => { if (!saving) e.currentTarget.style.background = "var(--accent-ink)"; }}
              onMouseOut={e => { if (!saving) e.currentTarget.style.background = saving ? "var(--ink-4)" : "var(--accent)"; }}>
                {saving ? "Saving…" : "Save Profile"}
              </button>
              <button onClick={handleCancel} disabled={saving} style={{
                padding: "12px 24px",
                background: "var(--surface-2)", color: "var(--ink-2)",
                border: "1px solid var(--hairline-strong)",
                borderRadius: "var(--r-sm)", fontSize: 15, fontWeight: 600,
                cursor: saving ? "default" : "pointer",
                fontFamily: "var(--font-sans)",
              }}>
                Cancel
              </button>
            </div>
          )}
        </div>

        {/* ── Change Password ── */}
        <div className="card" style={{ padding: "var(--card-pad)", marginBottom: 20 }}>
          <div className="eyebrow" style={{ marginBottom: 20 }}>Change Password</div>

          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>Current password</label>
            <input style={inputStyle} type="password" value={oldPw} placeholder="••••••••"
              onChange={e => setOldPw(e.target.value)} onFocus={focusIn} onBlur={focusOut} />
          </div>
          <div style={{ marginBottom: 14 }}>
            <label style={labelStyle}>New password</label>
            <input style={inputStyle} type="password" value={newPw1} placeholder="at least 10 chars, letters + numbers"
              onChange={e => setNewPw1(e.target.value)} onFocus={focusIn} onBlur={focusOut} autoComplete="new-password" />
          </div>
          <div style={{ marginBottom: 20 }}>
            <label style={labelStyle}>Confirm new password</label>
            <input style={inputStyle} type="password" value={newPw2} placeholder="repeat new password"
              onChange={e => setNewPw2(e.target.value)} onFocus={focusIn} onBlur={focusOut} />
          </div>

          {pwError && (
            <div style={{
              fontSize: 13.5, color: "oklch(0.52 0.115 22)",
              background: "oklch(0.93 0.04 22)", borderRadius: "var(--r-sm)",
              padding: "10px 14px", marginBottom: 14,
            }}>{pwError}</div>
          )}

          <button onClick={handleChangePassword} disabled={pwSaving} style={{
            width: "100%", padding: "11px 24px",
            background: pwSaving ? "var(--ink-4)" : "var(--surface-2)",
            color: pwSaving ? "var(--paper)" : "var(--ink-2)",
            border: "1px solid var(--hairline-strong)",
            borderRadius: "var(--r-sm)", fontSize: 15, fontWeight: 700,
            cursor: pwSaving ? "default" : "pointer",
            fontFamily: "var(--font-sans)", transition: "all 0.15s",
          }}
          onMouseOver={e => { if (!pwSaving) { e.currentTarget.style.background = "var(--surface)"; e.currentTarget.style.borderColor = "var(--ink-3)"; } }}
          onMouseOut={e => { if (!pwSaving) { e.currentTarget.style.background = "var(--surface-2)"; e.currentTarget.style.borderColor = "var(--hairline-strong)"; } }}>
            {pwSaving ? "Updating…" : "Update Password"}
          </button>
        </div>

        {/* ── Danger Zone — Delete Account ── */}
        <div className="card" style={{
          padding: "var(--card-pad)", marginBottom: 48,
          borderColor: showDelete ? "oklch(0.72 0.09 22)" : "var(--hairline)",
        }}>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 500,
            letterSpacing: "0.10em", textTransform: "uppercase",
            color: "oklch(0.58 0.095 22)", marginBottom: 12,
          }}>Danger Zone</div>

          <p style={{ fontSize: 14, color: "var(--ink-3)", marginBottom: 16, lineHeight: 1.6 }}>
            Permanently delete your account and all associated data. This cannot be undone.
          </p>

          {!showDelete ? (
            <button onClick={() => setShowDelete(true)} style={{
              padding: "10px 20px",
              background: "transparent",
              color: "oklch(0.52 0.115 22)",
              border: "1.5px solid oklch(0.75 0.08 22)",
              borderRadius: "var(--r-sm)", fontSize: 14, fontWeight: 700,
              cursor: "pointer", fontFamily: "var(--font-sans)", transition: "background 0.15s",
            }}
            onMouseOver={e => { e.currentTarget.style.background = "oklch(0.94 0.035 22)"; }}
            onMouseOut={e => { e.currentTarget.style.background = "transparent"; }}>
              Delete My Account
            </button>
          ) : (
            <div>
              <p style={{ fontSize: 13.5, color: "oklch(0.52 0.115 22)", marginBottom: 10, fontWeight: 600, lineHeight: 1.5 }}>
                Type your username <code style={{ background: "var(--surface-2)", padding: "1px 5px", borderRadius: 4 }}>{user.username}</code> to confirm:
              </p>
              <input
                style={{ ...inputStyle, marginBottom: 14, borderColor: "oklch(0.75 0.08 22)" }}
                type="text" value={deleteConfirm} placeholder={user.username}
                onChange={e => setDeleteConfirm(e.target.value)} onFocus={focusIn} onBlur={focusOut}
              />
              <div style={{ display: "flex", gap: 10 }}>
                <button onClick={handleDeleteAccount}
                  disabled={deleteConfirm !== user.username || deleting}
                  style={{
                    padding: "10px 20px", flex: 1,
                    background: (deleteConfirm === user.username && !deleting)
                      ? "oklch(0.52 0.115 22)" : "var(--ink-4)",
                    color: "var(--paper)", border: "none",
                    borderRadius: "var(--r-sm)", fontSize: 14, fontWeight: 700,
                    cursor: (deleteConfirm === user.username && !deleting) ? "pointer" : "default",
                    fontFamily: "var(--font-sans)", transition: "background 0.15s",
                  }}>
                  {deleting ? "Deleting…" : "Yes, delete my account"}
                </button>
                <button onClick={() => { setShowDelete(false); setDeleteConfirm(""); }} style={{
                  padding: "10px 20px",
                  background: "var(--surface-2)", color: "var(--ink-2)",
                  border: "1px solid var(--hairline-strong)",
                  borderRadius: "var(--r-sm)", fontSize: 14, fontWeight: 600,
                  cursor: "pointer", fontFamily: "var(--font-sans)",
                }}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}

window.ProfileScreen = ProfileScreen;
