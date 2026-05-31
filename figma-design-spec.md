# Figma Design Spec — Narrative Evolution Agent

## 1. Design Tokens

### Colors
| Token | Hex | Usage |
|---|---|---|
| `primary` | `#1f77b4` | Buttons, links, active states, default card left-border |
| `strengthening` | `#2ecc71` | Narrative card border — strengthening trend |
| `weakening` | `#e74c3c` | Narrative card border — weakening trend |
| `stable` | `#f39c12` | Narrative card border — stable trend |
| `bg-page` | `#ffffff` | Page background |
| `bg-secondary` | `#f0f2f6` | Sidebar, card backgrounds, input fills |
| `text-primary` | `#31333F` | Body text |
| `text-muted` | `#6c757d` | Captions, secondary labels |
| `divider` | `#e6e9ef` | Horizontal rules between cards |
| `success` | `#28a745` | Success alerts |
| `warning` | `#ffc107` | Warning alerts |
| `error` | `#dc3545` | Error alerts |
| `info` | `#17a2b8` | Info alerts |

### Typography
| Style | Font | Weight | Size | Line Height |
|---|---|---|---|---|
| App Title | Inter / system sans-serif | 700 | 28px | 36px |
| Tab Header (`st.header`) | Inter | 600 | 22px | 30px |
| Section Header (`st.subheader`) | Inter | 600 | 18px | 26px |
| Card Title (h3) | Inter | 600 | 16px | 24px |
| Body | Inter | 400 | 14px | 22px |
| Caption | Inter | 400 | 12px | 18px |
| Metric Value | Inter | 700 | 24px | 32px |
| Metric Label | Inter | 400 | 12px | 18px |
| Sidebar Label | Inter | 500 | 13px | 20px |
| Code block | JetBrains Mono / monospace | 400 | 13px | 20px |

### Spacing Scale
```
4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48px
```

### Border Radius
| Element | Radius |
|---|---|
| Cards / containers | 10px |
| Buttons | 6px |
| Input fields | 6px |
| Alerts | 6px |
| Tabs | 4px |
| Charts | 8px |

### Elevation / Shadows
| Level | Value |
|---|---|
| Cards | `0 1px 3px rgba(0,0,0,0.08)` |
| Modals / expanders | `0 4px 12px rgba(0,0,0,0.12)` |
| Sidebar | `2px 0 8px rgba(0,0,0,0.06)` |

---

## 2. Canvas & Layout

### Breakpoints
- **Desktop target:** 1440px wide (Figma frame)
- **Content max-width:** 1200px (centered)
- **Sidebar width:** 260px (fixed)
- **Main content:** `1440 - 260 = 1180px` (fluid)

### Grid
- **Columns:** 12
- **Gutter:** 24px
- **Margin:** 32px (left/right)

---

## 3. Global Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Top Bar (Streamlit chrome — minimal toolbar)               │
│  h: 52px, bg: #ffffff, border-bottom: 1px solid #e6e9ef    │
├──────────────────┬──────────────────────────────────────────┤
│  SIDEBAR         │  MAIN CONTENT AREA                       │
│  w: 260px        │  flex: 1                                 │
│  bg: #f0f2f6     │  bg: #ffffff                            │
│  px: 20px        │  px: 32px  pt: 24px                     │
│                  │                                          │
│  [Config panel]  │  [App title]                             │
│                  │  [Subtitle]                              │
│                  │  [Tab bar]                               │
│                  │  [Active tab content]                    │
└──────────────────┴──────────────────────────────────────────┘
```

---

## 4. Sidebar Component

**Container:** `w:260px`, `bg:#f0f2f6`, `px:20px`, `py:24px`

```
┌─────────────────────────┐
│  ⚙️ Configuration        │  ← Section header, 18px, #31333F
│                         │
│  User ID                │  ← Label, 13px
│  [default          ▽]   │  ← Text input, h:36px, bg:#fff, border:1px #d1d5db, radius:6px
│                         │
│  Hours to analyze       │  ← Label, 13px
│  [━━━━●━━━━━━━━━━━━━]   │  ← Slider, range 1–168, default 24
│  24 hours               │  ← Current value label, 12px, muted
│                         │
│  Minimum confidence     │  ← Label, 13px
│  [━●━━━━━━━━━━━━━━━━]   │  ← Slider, range 0.0–1.0, step 0.05, default 0.5
│  0.50                   │  ← Current value label, 12px, muted
└─────────────────────────┘
```

---

## 5. Page Header

```
┌─────────────────────────────────────────────────────────┐
│  🔮 Narrative Evolution Agent                           │
│  ← 28px bold, color #31333F                             │
│                                                         │
│  Detect emerging crypto narratives from whale wallet    │
│  activity and track their evolution                     │
│  ← 14px, color #6c757d, bold keywords                  │
└─────────────────────────────────────────────────────────┘
```

---

## 6. Tab Bar

**4 tabs, full-width, border-bottom on container**

```
[🔍 Detect Narratives] [📊 Narrative Dashboard] [⭐ My Tracked Narratives] [📈 Narrative History]
```

| State | Style |
|---|---|
| Active | bg: `#1f77b4`, text: `#ffffff`, radius: `4px 4px 0 0` |
| Inactive | bg: transparent, text: `#31333F`, border-bottom: none |
| Hover | bg: `#e8f0fb`, text: `#1f77b4` |

Tab bar container: `h:44px`, `border-bottom: 2px solid #1f77b4`

---

## 7. Tab 1 — Detect Narratives

### 7.1 Header + Info Alert
```
Detect Emerging Narratives          ← st.header, 22px, 600
┌─────────────────────────────────────────────────────┐
│ ℹ  Pulling live on-chain data from Elasticsearch    │
│    (last 24h)                                       │
└─────────────────────────────────────────────────────┘
← bg: #e8f4f8, border-left: 4px solid #17a2b8, radius:6px, px:16px, py:12px
```

### 7.2 Primary Action Button
```
┌────────────────────────────────┐
│   🔍 Detect Emerging Narratives │
└────────────────────────────────┘
← bg: #1f77b4, text: #fff, 14px 600, px:24px py:10px, radius:6px, w:full (or auto)
```

### 7.3 Signal Metrics Row (after detection)
**4-column grid, gutter 16px**

```
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ 🐋 Whale Txs │ │ 🧠 Smart Money│ │ 🔄 Token Flows│ │ 🌉 Bridge    │
│     142      │ │      89      │ │      67      │ │      34      │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ 🏦 Conc.    │ │ 📊 Vol Spikes│ │ 🌱 Holder Grw│ │ 💧 DEX Conc. │
│      23      │ │      45      │ │      78      │ │      12      │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

**Metric card specs:**
- `bg: #f0f2f6`, `border-radius: 10px`, `px:20px`, `py:16px`
- Metric value: `24px`, `700`, `#31333F`
- Metric label: `12px`, `400`, `#6c757d`

### 7.4 Success Alert
```
┌─────────────────────────────────────────────────────┐
│ ✅ Loaded 490 documents across 8 signal types       │
└─────────────────────────────────────────────────────┘
← bg: #d4edda, border-left: 4px solid #28a745, radius:6px
```

### 7.5 Narrative Card
Repeat per detected narrative. Left border color varies by momentum trend.

```
┌──────────────────────────────────────────────────────────┐  ← bg:#f0f2f6, radius:10px, 
│ ←  5px solid #2ecc71 (strengthening)                    │     border-left:5px, mb:16px
│                                                          │
│  ┌─ col 2/3 ──────────────────┐  ┌─ col ─┐  ┌─ col ─┐  │
│  │ 📈 1. DeFi Re-emergence    │  │       │  │       │  │
│  │ ← 16px, 600               │  │  ⭐   │  │  📖   │  │
│  │ Category: DeFi            │  │ Track │  │Details│  │
│  │ Strength: High | 87.0%    │  │       │  │       │  │
│  │ Momentum: Strengthening   │  └───────┘  └───────┘  │
│  │           (72.0%)         │                         │
│  │ Driven by: whale_txs, ... │  ← caption, 12px, muted│
│  └────────────────────────────┘                         │
└──────────────────────────────────────────────────────────┘
```

**Button specs (Track / Details):**
- `w:80px`, `h:36px`, `radius:6px`, `14px`, `500`
- Track: `bg:#fff`, `border: 1px solid #1f77b4`, `text:#1f77b4`
- Details: `bg:#f0f2f6`, `border: 1px solid #d1d5db`, `text:#31333F`

### 7.6 Expanded Detail Panel (expander)
```
┌──── 📊 Full Details ────────────────────────────────────┐
│                                                          │
│  Key Evidence:                    ← 14px, 600           │
│  • ETH whale wallets rotated into DeFi protocols        │
│  • 340% volume increase on Uniswap                     │
│                                                          │
│  Implications:                                           │
│  [paragraph text, 14px, 400]                            │
│                                                          │
│  Top Tokens: UNI, AAVE, COMP, CRV                       │
│                                                          │
│  Retail Considerations:                                  │
│  [paragraph text]                                       │
│                                                          │
│  Momentum: strength +2, confidence +8.0%               │
│                                   ← 14px, muted        │
└──────────────────────────────────────────────────────────┘
← bg:#fff, border:1px solid #e6e9ef, radius:10px, px:24px, py:20px
```

---

## 8. Tab 2 — Narrative Dashboard

### 8.1 Stats Row
3 metric cards, equal-width columns, same card specs as §7.3

```
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ 📍 Total         │ │ ⭐ Tracked        │ │ 📈 Strengthening │
│   Narratives     │ │                  │ │                  │
│      12          │ │       4          │ │        5         │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

### 8.2 All Current Narratives Table

**Section header:** `All Current Narratives`, 18px, 600

```
┌──────────────────────────────────────────────────────────────────┐
│ Name         │ Category  │ Strength │ Confidence │ Momentum │  ⭐│
├──────────────┼───────────┼──────────┼────────────┼──────────┼───┤
│ DeFi Re-...  │ DeFi      │ High     │ 87.0%      │ Strength │  ⭐│
│ L2 Adoption  │ Scaling   │ Medium   │ 71.0%      │ Stable   │    │
│ ...          │ ...       │ ...      │ ...        │ ...      │    │
└──────────────┴───────────┴──────────┴────────────┴──────────┴───┘
```

- Table: full-width, alternating row bg (`#fff` / `#f9fafb`)
- Header row: `bg:#f0f2f6`, `12px`, `600`, `uppercase`, `letter-spacing:0.5px`
- Row height: `44px`, `border-bottom: 1px solid #e6e9ef`
- ⭐ column: `20px` fixed width

### 8.3 Strengthening Narratives List

**Section header:** `📈 Strengthening Narratives`, 18px, 600

```
┌───────────────────────────────────────────────┬──────────┐
│ DeFi Re-emergence (DeFi)                      │ 👁️ Watch │
│ Confidence: 87.0% | Momentum Score: 72.0%     │          │
├───────────────────────────────────────────────┼──────────┤
│ L2 Mass Adoption (Scaling)                    │ 👁️ Watch │
│ Confidence: 71.0% | Momentum Score: 65.0%     │          │
└───────────────────────────────────────────────┴──────────┘
```

- Name: `14px`, `600`, `#31333F`
- Caption: `12px`, `400`, `#6c757d`
- Watch button: `w:88px`, `h:32px`, same secondary button style

---

## 9. Tab 3 — My Tracked Narratives

### Narrative Tracked Card

```
┌──────────────────────────────────────────────────────────┐
│  ┌─ col 3/5 ───────────────────────┐  ┌──────┐  ┌─────┐ │
│  │ ### DeFi Re-emergence           │  │ 📈   │  │  ❌ │ │
│  │ Category: DeFi | Strength: High │  │History│  │Untrk│ │
│  │ Last updated: 2026-05-30 14:23  │  └──────┘  └─────┘ │
│  └─────────────────────────────────┘                     │
│                                                          │
│  ▼ 📊 7-Day History  [expander, expanded when toggled]  │
│  ┌──────────────────────────────────────────────────┐   │
│  │  [Plotly line chart: Confidence + Momentum]      │   │
│  │  h:400px, dual traces, legend bottom             │   │
│  └──────────────────────────────────────────────────┘   │
├─────────────────────────────────── divider ─────────────┤
```

**Chart specs:**
- Container: full-width, `h:400px`, `radius:8px`, `border:1px solid #e6e9ef`
- Confidence trace: `color:#1f77b4`, `strokeWidth:2`, markers enabled
- Momentum trace: `color:#e74c3c`, `strokeWidth:2`, markers enabled
- Background: `#ffffff`, Grid: `#f0f2f6`

---

## 10. Tab 4 — Narrative History

### Controls Row

```
┌─────────────────────────────────────────────────┐
│ Select a narrative to view its evolution        │  ← label
│ [DeFi Re-emergence                          ▼]  │  ← selectbox, h:40px
└─────────────────────────────────────────────────┘

Days of history to show
[━━━━━━━●━━━━━━━━━━━━━━━━━━]    7
```

### Chart 1 — Confidence Trend
```
┌──────────────────────────────────────────────────────┐
│  DeFi Re-emergence - Confidence Trend               │
│  [Plotly line chart, markers=True]                  │
│  x-axis: Time, y-axis: Confidence (0.0–1.0)         │
│  h:400px                                            │
└──────────────────────────────────────────────────────┘
```

### Chart 2 — Momentum Trend
```
┌──────────────────────────────────────────────────────┐
│  DeFi Re-emergence - Momentum Trend                 │
│  [Plotly line chart, markers=True]                  │
│  x-axis: Time, y-axis: Momentum (0.0–1.0)           │
│  h:400px                                            │
└──────────────────────────────────────────────────────┘
```

### Stats Row
3 metric cards (same spec as §7.3):
- Avg Confidence
- Max Confidence
- Current Momentum

---

## 11. Alert / Notification Components

| Type | BG | Left border | Icon |
|---|---|---|---|
| Info | `#e8f4f8` | `#17a2b8` | ℹ️ |
| Success | `#d4edda` | `#28a745` | ✅ |
| Warning | `#fff3cd` | `#ffc107` | ⚠️ |
| Error | `#f8d7da` | `#dc3545` | ❌ |

All: `radius:6px`, `px:16px`, `py:12px`, `14px`, `mb:16px`

---

## 12. Spinner / Loading State

```
┌──────────────────────────────────────────────────┐
│                                                  │
│     ◌  Fetching on-chain signals from            │
│        Elasticsearch...                          │
│                                                  │
└──────────────────────────────────────────────────┘
← overlay on content area, bg: rgba(255,255,255,0.8)
← spinner: animated circle, color #1f77b4, size 24px
← text: 14px, #31333F, centered
```

---

## 13. Figma Component Checklist

### Atoms
- [ ] Color styles (all tokens in §1)
- [ ] Text styles (all in §1 typography table)
- [ ] Button/Primary
- [ ] Button/Secondary
- [ ] Button/Danger (Untrack ❌)
- [ ] Input/Text
- [ ] Input/Select (dropdown)
- [ ] Slider
- [ ] Badge/Metric card
- [ ] Alert/Info, Alert/Success, Alert/Warning, Alert/Error
- [ ] Divider

### Molecules
- [ ] Narrative card (with variant prop: `strengthening | weakening | stable | new`)
- [ ] Strengthening item row
- [ ] Tracked narrative card
- [ ] Stats row (3-column metric group)
- [ ] Signal metrics grid (2-row × 4-col)
- [ ] Tab bar

### Organisms
- [ ] Sidebar/Configuration panel
- [ ] Page header
- [ ] Tab 1 content frame
- [ ] Tab 2 content frame
- [ ] Tab 3 content frame
- [ ] Tab 4 content frame

### Pages (Figma Frames — 1440×900px each)
1. **Detect Narratives — Empty state** (before button click)
2. **Detect Narratives — Loading** (spinner overlay)
3. **Detect Narratives — Results** (signal metrics + 3 narrative cards, one expanded)
4. **Narrative Dashboard** (stats + table + strengthening list)
5. **My Tracked Narratives** (2 tracked cards, one with chart expanded)
6. **Narrative History** (both charts visible + stats row)
7. **Error / Config Required state** (full-page error with code block)

---

## 14. Suggested Figma File Structure

```
📁 Narrative Evolution Agent
  📁 _Design Tokens
    🎨 Colors
    📝 Typography
    📐 Spacing
  📁 Components
    📁 Atoms
    📁 Molecules
    📁 Organisms
  📁 Pages
    🖼️ 01 - Detect (Empty)
    🖼️ 02 - Detect (Loading)
    🖼️ 03 - Detect (Results)
    🖼️ 04 - Dashboard
    🖼️ 05 - Tracked
    🖼️ 06 - History
    🖼️ 07 - Error State
  📁 Prototype Flows
    🔗 Main user flow
```
