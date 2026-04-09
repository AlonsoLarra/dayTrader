# Mobile UI Requirements — dayTrader
**Spec-Driven Development**

---

## Context

The dayTrader app is a React + Tailwind CSS crypto trading dashboard built primarily for desktop/tablet use. From the mobile screenshot provided (≈375px viewport), multiple layout problems are visible:

- The header is critically overflowed: logo, 3 nav tabs, wallet badge, Auto-Trade button, Close All button, and logout icon are all crammed into one row — resulting in truncated text and unusable touch targets.
- The content pane (BacktestPanel/Strategy) only occupies the left ~290px; the right half of the screen is blank white.
- Font sizes and tap targets are too small for mobile ergonomics (< 44px hit areas).
- No mobile-specific navigation pattern (hamburger/bottom nav) exists.
- Modals are not safe for small screens (can overflow viewport).

These requirements define the changes needed to make the UI fully functional and visually sound on mobile devices (320–767px), while preserving all existing desktop behavior.

---

## Tech Stack Reference

| Concern | Current |
|---|---|
| Framework | React 18 + TypeScript |
| Styling | Tailwind CSS 3 (utility classes only, no CSS modules) |
| Breakpoints | Tailwind defaults: `sm` 640px, `md` 768px, `lg` 1024px |
| Charts | Recharts (`ResponsiveContainer`) |
| Icons | Lucide React |
| Routing | Tab state in `App.tsx` (no React Router) |

**Mobile target**: 320px–767px (below Tailwind `md` breakpoint)

---

## REQ-001 — Responsive Header / Navigation

**Problem**: Header row overflows on mobile; all controls compete for ~375px.

### Mobile (< `md` / < 768px)

Display a **two-row header**:

- **Row 1**: Logo ("dayTrader" wordmark) on the left; a compact right cluster containing only the **wallet balance pill** (e.g., "PAPER · $100") and a **hamburger/menu icon** (Lucide `Menu`).
- **Row 2**: A **bottom navigation bar** fixed to the bottom of the viewport with 3 icon+label tabs: Dashboard, Strategy, Trades. Active tab highlighted with blue underline/fill.

The **Auto-Trade**, **Close All (Kill Switch)**, and **Logout** actions move into a **slide-in drawer** triggered by the hamburger icon in Row 1.

The wallet detailed dropdown (paper/live toggle, balance editor) remains accessible from the wallet pill tap.

- Bottom nav bar height: `56px`; icons `20px`; labels `text-xs`
- Bottom nav must account for iOS safe-area-inset-bottom (`env(safe-area-inset-bottom)`)

### Desktop (≥ `md`)

Existing single-row header unchanged. Bottom nav hidden.

**Acceptance criteria**:
- [ ] All 3 tabs are reachable on mobile without horizontal scrolling
- [ ] Auto-Trade, Close All, Logout are accessible via drawer
- [ ] Wallet balance visible in header at all times
- [ ] No header content is clipped or overflowed on 320px viewport

**Files**: `frontend/src/App.tsx`, `frontend/src/components/WalletHeader.tsx`

---

## REQ-002 — Full-Width Content Layout

**Problem**: Strategy/BacktestPanel content only fills the left portion of the mobile screen; right side is empty.

**Specification**:
- All page content must span `w-full` on mobile
- Remove any fixed pixel widths or `max-w-*` constraints that prevent full-width rendering below `md`
- The `BacktestPanel` two-column layout (if any) must stack to single column on mobile
- Ensure `min-w-0` on flex children so text truncates rather than overflows
- The `Dashboard` stats grid should be `grid-cols-1` below `sm`, and `grid-cols-2` for `sm`–`md`

**Acceptance criteria**:
- [ ] BacktestPanel content fills 100% of viewport width on 375px
- [ ] No horizontal whitespace gaps on any mobile view
- [ ] Dashboard stats grid readable on 320px without overflow

**Files**: `frontend/src/App.tsx`, `frontend/src/components/BacktestPanel.tsx`, `frontend/src/components/Dashboard.tsx`

---

## REQ-003 — Touch-Friendly Tap Targets

**Problem**: Buttons use `px-3 py-1.5` which yields ~28–32px height — below the 44px minimum recommended for touch.

**Specification**:
- All interactive elements (buttons, tab items, list rows) must have a minimum tap target of **44×44px** on mobile
- Button variants on mobile: `py-2.5 px-4` minimum (≈40px height acceptable with large width)
- AgentCard action buttons (play/stop/kill): at least `h-9 w-9` on mobile
- Pair rows in BacktestPanel / MarketScanner: `min-h-[48px]` row height
- Input fields: `py-2.5` minimum to ensure comfortable tap

**Acceptance criteria**:
- [ ] No tappable element measures less than 44px in either dimension on mobile
- [ ] AgentCard controls usable with a thumb without precision tapping
- [ ] Form inputs easily selectable on first tap

**Files**: `frontend/src/components/AgentCard.tsx`, `frontend/src/components/BacktestPanel.tsx`, `frontend/src/components/AutoTradeModal.tsx`, `frontend/src/components/CreateAgentModal.tsx`

---

## REQ-004 — Mobile-Safe Modals

**Problem**: Modals using `max-w-lg mx-4` can overflow on 320px screens; tall modals have no scroll containment.

**Specification**:
- Modal container: `w-[calc(100%-2rem)] max-w-lg` (ensures gutter on any screen)
- Modal body must be scrollable: `max-h-[80vh] overflow-y-auto` on inner content area
- On mobile, modals should anchor to the **bottom** of the screen as a **bottom sheet** (`fixed bottom-0 inset-x-0 rounded-t-2xl`) rather than floating centered. Above `md`: keep existing centered overlay behavior.
- Bottom sheet handle indicator: `w-10 h-1 bg-gray-600 rounded-full mx-auto mt-2 mb-4`
- Backdrop tap closes the modal/sheet

**Acceptance criteria**:
- [ ] Modals never overflow viewport width on 320px
- [ ] Modal content scrollable when taller than viewport
- [ ] Bottom sheet handle visible; backdrop tap dismisses
- [ ] Desktop modal behavior unchanged

**Files**: `frontend/src/components/AutoTradeModal.tsx`, `frontend/src/components/CreateAgentModal.tsx`

---

## REQ-005 — Typography & Readability

**Problem**: Text is rendered at `text-xs` / `text-sm` sizes which become difficult to read on mobile at arm's length.

**Specification**:
- **Minimum body text size on mobile**: `text-sm` (14px). `text-xs` (12px) permitted only for metadata/labels.
- **Pair score/RSI values** in BacktestPanel: upgrade to `text-sm font-medium` on mobile
- **Status badges** (WAITING, HOLDING): `px-2 py-0.5 text-xs rounded-full` minimum — do not shrink below 12px
- **Currency/price values**: `font-mono tabular-nums` preserved; at least `text-sm`
- **Section headers**: `text-base font-semibold` on mobile (currently `text-sm font-medium`)

**Acceptance criteria**:
- [ ] No body text smaller than 14px on mobile
- [ ] RSI values and scores legible without zooming
- [ ] Status badges remain visible on narrow cards

**Files**: `frontend/src/components/BacktestPanel.tsx`, `frontend/src/components/Dashboard.tsx`, `frontend/src/components/PositionsPanel.tsx`, `frontend/src/components/TradeLog.tsx`

---

## REQ-006 — Horizontal Scroll & Table Handling

**Problem**: TradeLog table requires horizontal scrolling on mobile but lacks visual affordance; PriceBoard ticker may clip.

**Specification**:
- `TradeLog` table wrapper: add `overflow-x-auto -mx-4 px-4` (bleed to edge) with a subtle right-fade gradient overlay to indicate more content horizontally
- Add `min-w-[600px]` to the `<table>` to preserve column integrity
- On mobile, hide lower-priority columns with `hidden sm:table-cell` (e.g., Strategy column in TradeLog)
- **PriceBoard**: On mobile, hide the OHLCV chart by default. Show only the ticker strip. Add a "Show Chart" chevron toggle to expand.

**Acceptance criteria**:
- [ ] TradeLog scrolls horizontally without clipping; right-fade gradient visible
- [ ] Table columns remain aligned during scroll
- [ ] PriceBoard renders without overflow on 375px; chart toggleable

**Files**: `frontend/src/components/TradeLog.tsx`, `frontend/src/components/PriceBoard.tsx`

---

## REQ-007 — Collapsible Sections on Mobile

**Problem**: Long scrollable lists (market scanner pairs, agent cards) are hard to navigate on mobile without visual hierarchy.

**Specification**:
- **BacktestPanel — Pairs evaluated list**: On mobile, show first 5 pairs collapsed under a "Show all N pairs" toggle button. Expanding reveals full list with smooth `max-h` CSS transition.
- **AgentCard logs**: Already expandable — ensure the expand chevron is `h-10 w-10` tap target on mobile.
- **PositionsPanel**: If more than 3 open positions, show a "See all (N)" button on mobile.

**Acceptance criteria**:
- [ ] Pairs list collapsed to 5 items by default on mobile; expands on tap
- [ ] AgentCard expand/collapse chevron is 40px tap target
- [ ] PositionsPanel shows "See all" when > 3 positions on mobile

**Files**: `frontend/src/components/BacktestPanel.tsx`, `frontend/src/components/PositionsPanel.tsx`, `frontend/src/components/AgentCard.tsx`

---

## REQ-008 — Viewport Meta & Body Scroll

**Problem**: Body may allow unintentional pinch-zoom; body height should fill viewport with content scrolling to enable a fixed bottom nav.

**Specification**:
- `index.html` viewport meta: add `viewport-fit=cover` for notch/Dynamic Island support:
  ```html
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
  ```
- Add to `index.css`:
  ```css
  html, body { height: 100%; overflow: hidden; }
  #root { height: 100%; overflow-y: auto; }
  ```
  This makes the root scroll rather than the body, enabling a fixed bottom nav to stay pinned.
- Bottom nav: `padding-bottom: env(safe-area-inset-bottom)` for iPhone home indicator clearance.

**Acceptance criteria**:
- [ ] Fixed bottom nav stays pinned while content scrolls on iOS/Android
- [ ] No content hidden under notch or home indicator
- [ ] No double scrollbar on desktop

**Files**: `frontend/index.html`, `frontend/src/index.css`

---

## REQ-009 — WalletHeader Compact Mode

**Problem**: The WalletHeader dropdown is too wide for mobile; PAPER/LIVE toggle takes up excessive header space.

**Specification**:
- **Mobile pill** (per REQ-001 Row 1): Display `PAPER · MXN 100.00` in a compact badge:
  ```
  bg-gray-800 border border-gray-700 rounded-full px-3 py-1 text-xs font-mono
  ```
- Tapping the pill opens the full wallet controls as a bottom sheet (REQ-004 pattern)
- **Desktop**: Existing WalletHeader behavior unchanged

**Acceptance criteria**:
- [ ] Wallet pill fits in header alongside logo on 320px
- [ ] Full wallet controls accessible via pill tap on mobile
- [ ] Paper/Live toggle functional within bottom sheet

**Files**: `frontend/src/components/WalletHeader.tsx`

---

## REQ-010 — PriceBoard Mobile Optimization

**Problem**: The PriceBoard (ticker + charts) takes significant vertical space on mobile; horizontal scroll is not obvious.

**Specification**:
- On mobile: render PriceBoard as a **horizontal scrolling chip row** of coin prices only:
  - Each chip: symbol + price + 24h % change
  - Chip style: `bg-gray-800 rounded-lg px-3 py-2 shrink-0 min-w-[90px]`
- A **"Charts"** button at the end of the chip row expands a full-width chart panel below
- On `md`+: existing PriceBoard layout unchanged

**Acceptance criteria**:
- [ ] Chips scroll horizontally without wrapping
- [ ] Symbol, price, and % change visible per chip
- [ ] Chart expandable via "Charts" button

**Files**: `frontend/src/components/PriceBoard.tsx`

---

## Implementation Priority Order

| Priority | REQ | Rationale |
|---|---|---|
| 1 | REQ-008 | Viewport/scroll foundation — enables fixed bottom nav |
| 2 | REQ-001 | Header + bottom nav — highest user impact, changes nav paradigm |
| 3 | REQ-002 | Full-width layout — unblocks other layout fixes |
| 4 | REQ-003 | Touch targets — affects all interactive components |
| 5 | REQ-009 | WalletHeader compact — depends on REQ-001 structure |
| 6 | REQ-004 | Modal bottom sheets — self-contained |
| 7 | REQ-010 | PriceBoard chip row — self-contained |
| 8 | REQ-006 | Table handling — self-contained |
| 9 | REQ-007 | Collapsible sections — depends on REQ-002 layout |
| 10 | REQ-005 | Typography — refinement pass |

---

## Verification Checklist

- [ ] Browser DevTools — iPhone SE (375×667) and iPhone 14 Pro (390×844); test all breakpoints
- [ ] Tab navigation — all 3 tabs reachable from bottom nav on mobile; header nav visible on desktop
- [ ] Touch targets — Lighthouse accessibility audit; no element < 44px
- [ ] Modal behaviour — AutoTradeModal and CreateAgentModal on 375px: bottom sheet, scrollable body, backdrop close
- [ ] Horizontal scroll — TradeLog and PriceBoard scroll without clipping
- [ ] Safe area — test `env(safe-area-inset-bottom)` in DevTools device simulation
- [ ] Desktop regression — all existing layouts unchanged at 1280px viewport
