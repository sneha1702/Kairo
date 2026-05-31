/* ============================================================
   Kairo — content model
   Everything is an INTERPRETATION, never a metric-first feed.
   ============================================================ */
window.KAIRO = (function () {

  const user = {
    name: "Sarah",
    date: "Friday, May 30",
    follows: ["ETH", "ARB", "LINK", "RNDR"],
    summary: { developments: 2, strengthening: 1, risks: 0 },
  };

  // The single market story of the day
  const story = {
    eyebrow: "Today's Market Story",
    headline: "Money kept moving into Ethereum's Layer-2 ecosystems",
    short: "Capital continued rotating into Ethereum scaling networks for a fourth straight session.",
    why: "Institutional wallets increased exposure to scaling infrastructure as fees stayed low and the ETF conversation gained momentum.",
    expanded: "Large, slow-moving wallets accumulated ARB and OP while trimming stablecoin balances — a pattern that has now repeated across most of the last twelve weeks. It reads less like a single headline reaction and more like sustained positioning ahead of expected scaling activity.",
    assets: ["ETH", "ARB", "OP"],
    confidence: "High",
    confidenceNote: "Multiple independent flows point the same direction",
    trend: { label: "12-week trend", id: "l2-rotation" },
  };

  // Card 2 — contextual exposure, NOT prices
  const holdings = [
    { sym: "ETH",  dir: "up",   exposure: "Positive exposure", note: "Core beneficiary of the L2 story", force: "smart-money" },
    { sym: "ARB",  dir: "up",   exposure: "Direct beneficiary", note: "Largest single inflow target today", force: "smart-money" },
    { sym: "LINK", dir: "flat", exposure: "No meaningful impact", note: "Not linked to today's flows", force: null },
    { sym: "RNDR", dir: "flat", exposure: "Unrelated to today", note: "Tracking a separate AI narrative", force: "narrative" },
  ];

  // Card 3 — events that crossed the relevance threshold
  const events = [
    {
      force: "regulation",
      title: "European digital-asset framework got new implementation guidance",
      impact: "Potentially positive for compliant infrastructure projects.",
      assets: ["ETH", "ARB"],
      when: "2h ago",
    },
    {
      force: "smart-money",
      title: "Top-1% wallets increased ARB allocation by 8%",
      impact: "Supports the ongoing Layer-2 rotation rather than starting a new one.",
      assets: ["ARB"],
      when: "5h ago",
    },
  ];

  // Card 4 — trend context (noise vs pattern)
  const trendContext = {
    title: "L2 Capital Rotation",
    rows: [
      { label: "Today",   value: "+$95M",  tone: "pos" },
      { label: "7 days",  value: "+$420M", tone: "pos" },
      { label: "90 days", value: "Strong positive", tone: "pos" },
    ],
    interpretation: "This looks like sustained positioning, not a short-term spike. Today's move fits a pattern that's been building for weeks.",
  };

  // Card 5 — watch next (forward, never predictive)
  const watch = {
    title: "AI Infrastructure",
    reason: "Whale accumulation rose for the third consecutive week.",
    status: "emerging",
    assets: ["RNDR", "TAO"],
  };

  // ---- Forces taxonomy ----
  const forces = {
    "smart-money": { label: "Smart Money",   blurb: "Whales & funds positioning", color: "lav",   icon: "brain" },
    "regulation":  { label: "Regulation",    blurb: "ETF news, laws, approvals",   color: "denim", icon: "scale" },
    "infra":       { label: "Infrastructure",blurb: "L2 adoption, fees, throughput", color: "teal", icon: "layers" },
    "liquidity":   { label: "Liquidity",     blurb: "Stablecoin & exchange flows", color: "sage",  icon: "drop" },
    "narrative":   { label: "Narrative",     blurb: "AI hype, memecoin cycles",    color: "peach", icon: "spark" },
    "rotation":    { label: "Rotation",      blurb: "BTC → ETH → L2 → AI flows",   color: "rose",  icon: "swap" },
  };

  // ---- Narrative status system ----
  const statuses = {
    emerging:      { label: "Emerging",      tone: "denim", dot: "denim" },
    strengthening: { label: "Strengthening", tone: "sage",  dot: "sage"  },
    established:    { label: "Established",   tone: "accent",dot: "accent"},
    cooling:       { label: "Cooling",       tone: "ink-3", dot: "neutral"},
    breaking:      { label: "Breaking down", tone: "rose",  dot: "rose"  },
  };

  // ---- The ongoing tracked narrative (the "Netflix series") ----
  const tracker = {
    title: "L2 Adoption Story",
    day: 14,
    status: "established",
    strength: 8.3,
    delta: "+0.4",
    summary: "Capital has rotated into Ethereum Layer-2 networks for the better part of three months. What began as speculative interest now reads as sustained institutional positioning.",
    forces: ["smart-money", "infra", "regulation"],
    assets: ["ETH", "ARB", "OP"],
    // strength curve over recent days (0–10)
    curve: [5.2, 5.4, 5.1, 5.8, 6.3, 6.1, 6.7, 7.2, 7.0, 7.5, 7.8, 7.6, 7.9, 8.3],
    // recent "episodes"
    episodes: [
      { day: 14, date: "May 30", headline: "Institutional wallets add ARB and OP",
        body: "Top-1% wallets increased L2 allocation by 8% while trimming stablecoins — the cleanest accumulation signal of the cycle so far.",
        force: "smart-money", strength: 8.3 },
      { day: 12, date: "May 28", headline: "ETF conversation widens to include staking",
        body: "Regulatory guidance hinted at clearer treatment for staking, strengthening the case for compliant L2 infrastructure.",
        force: "regulation", strength: 7.9 },
      { day: 9, date: "May 25", headline: "Fees hold near cycle lows",
        body: "Sustained low gas costs kept on-chain DeFi activity elevated, reinforcing the usage side of the story.",
        force: "infra", strength: 7.5 },
      { day: 6, date: "May 22", headline: "First sign of stablecoin → L2 rotation",
        body: "Exchange data showed stablecoins leaving for L2 tokens rather than BTC — an early marker this was rotation, not fresh capital.",
        force: "rotation", strength: 6.7 },
      { day: 1, date: "May 17", headline: "Narrative re-opened",
        body: "After a quiet April, a cluster of mid-size accumulation events re-opened the Layer-2 story Kairo had been tracking since winter.",
        force: "smart-money", strength: 5.2 },
    ],
  };

  // Other live narratives (for the Narratives index)
  const narratives = [
    { id: "l2-rotation", title: "L2 Adoption Story",      status: "established",   strength: 8.3, day: 14, assets: ["ETH","ARB","OP"], force: "infra" },
    { id: "ai-infra",    title: "AI Infrastructure",      status: "strengthening", strength: 6.4, day: 21, assets: ["RNDR","TAO"],      force: "narrative" },
    { id: "rwa",         title: "Real-World Assets",      status: "emerging",      strength: 4.1, day: 5,  assets: ["LINK","ONDO"],     force: "regulation" },
    { id: "meme",        title: "Memecoin Speculation",   status: "cooling",       strength: 3.2, day: 38, assets: ["DOGE","WIF"],      force: "narrative" },
  ];

  // ---- Pattern Memory (historical cycles) ----
  const history = {
    title: "L2 Inflow Cycles",
    subtitle: "How today's story compares with every time it has happened before",
    cycles: [
      { name: "Cycle 1", span: "Jan – Feb", kind: "Speculative",   peak: 6.1, durationWeeks: 6,
        note: "A short, sharp spike driven by retail speculation. Faded as quickly as it arrived.", current: false, force: "narrative" },
      { name: "Cycle 2", span: "Apr – May", kind: "Institutional", peak: 7.4, durationWeeks: 7,
        note: "Slower to build but far steadier — the first time large wallets led the move.", current: false, force: "smart-money" },
      { name: "Current", span: "Mar – now", kind: "Institutional", peak: 8.3, durationWeeks: 12,
        note: "Three consecutive months of inflows. The longest and most sustained cycle Kairo has on record.", current: true, force: "smart-money" },
    ],
    interpretation: "Each cycle has been longer and steadier than the last. The current one is the most sustained on record — a sign this has shifted from speculation toward structural positioning.",
  };

  return { user, story, holdings, events, trendContext, watch, forces, statuses, tracker, narratives, history };
})();
