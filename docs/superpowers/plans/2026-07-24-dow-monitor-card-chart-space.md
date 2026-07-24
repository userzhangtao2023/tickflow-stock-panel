# Dow Monitor Card Chart Space Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the compact multi-stock card density while making the mini K-line the card's dominant visual area.

**Architecture:** Preserve the existing `DowMonitorCard` data and interaction boundaries. Reflow only its summary markup into two compact rows, reduce the timeframe-control height, and pass an explicit 180-pixel height to the existing `DowMiniChart`; no backend or Dow semantics change.

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Vitest, Testing Library, ECharts

## Global Constraints

- `REQ-DOW-WATCH-UI-001` remains the active stable requirement.
- The card must keep code, name, price, percentage change, quote time, success time, switch, all five timeframes, latest Chinese action/shape, and detail opening.
- The mini K-line height must be 180 pixels and must remain clickable for the complete chart.
- Trend lines, acceleration lines, signals, freshness gating, and notification semantics must not change.
- Acceptance is limited to the existing 01347.HK monitor card before applying the layout in production.

---

### Task 1: Lock and implement the compact card allocation

**Files:**
- Modify: `docs/superpowers/specs/2026-07-23-dow-realtime-watch-panel-design.md`
- Modify: `frontend/src/pages/DowMonitor.test.tsx`
- Modify: `frontend/src/components/dow-monitor/DowMonitorCard.tsx`

**Interfaces:**
- Consumes: `DowMonitorOverviewSymbol`, `DowTimeframe`, and the existing `DowMiniChart({ chart, testId, height })` interface.
- Produces: a `data-layout="compact-two-row"` card summary and an explicitly 180-pixel-high mini chart.

- [ ] **Step 1: Write the failing layout test**

Add the following case beside the existing compact-card tests:

```tsx
it('keeps a compact two-row summary and gives the mini K-line 180 pixels', () => {
  render(<DowMonitor />)

  const card = screen.getByTestId('card-01347.HK')
  expect(within(card).getByTestId('card-summary-01347.HK')).toHaveAttribute(
    'data-layout',
    'compact-two-row',
  )
  expect(within(card).getByText('行情 2026-07-23 07:20Z')).toBeInTheDocument()
  expect(within(card).getByText('成功 2026-07-23 23:54Z')).toBeInTheDocument()
  expect(within(card).getByTestId('mini-chart-01347.HK-5m')).toHaveStyle({
    height: '180px',
  })
})
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
npm.cmd run test -- --run frontend/src/pages/DowMonitor.test.tsx
```

Expected: FAIL because `card-summary-01347.HK` does not exist and the mini chart still uses its 96-pixel default.

- [ ] **Step 3: Reflow the summary and enlarge the existing chart**

Replace the card's current summary wrapper with this two-row grid, retaining the existing value calculations and event handlers:

```tsx
<div
  data-testid={`card-summary-${item.symbol}`}
  data-layout="compact-two-row"
  className="grid grid-cols-[minmax(0,1fr)_auto_auto] grid-rows-2 items-center gap-x-2 px-2.5 py-1.5"
>
  <div className="flex min-w-0 items-center gap-2">
    <span className="shrink-0 font-mono text-sm font-semibold tracking-wide">
      {item.symbol}
    </span>
    {name && <span className="truncate text-xs text-secondary">{name}</span>}
  </div>
  {/* Existing switch and remove buttons remain in row 1. */}
  <div className="col-span-3 row-start-2 mt-0.5 flex min-w-0 items-baseline gap-2 overflow-hidden">
    <span className="shrink-0 font-mono text-base tabular-nums">
      {price == null ? '—' : price.toFixed(2)}
    </span>
    {/* Existing change, quote time, and success time remain on this row. */}
  </div>
</div>
```

Change each timeframe button from `h-6` to `h-5`, reduce the timeframe wrapper's bottom padding from `pb-1.5` to `pb-1`, and render the chart through:

```tsx
<DowMiniChart
  chart={selectedState?.chart ?? {}}
  testId={`mini-chart-${item.symbol}-${timeframe}`}
  height={180}
/>
```

- [ ] **Step 4: Run frontend verification and verify GREEN**

Run:

```powershell
npm.cmd run test -- --run frontend/src/pages/DowMonitor.test.tsx
npm.cmd run test -- --run
npm run build
```

Expected: the focused test, complete frontend suite, and production build all pass.

- [ ] **Step 5: Record semantic acceptance and independent review**

Update `docs/acceptance/2026-07-23-dow-realtime-watch-panel.md` with the 01347.HK visual evidence: two compact summary rows, five visible timeframe controls, 180-pixel mini K-line, unchanged bottom action/shape, and unchanged chart semantics.

Update `docs/reviews/2026-07-23-dow-realtime-watch-panel-review.md` with a fresh requirement-to-evidence review confirming `REQ-DOW-WATCH-UI-001` remains fully covered and no backend/Dow files changed.

- [ ] **Step 6: Run specification verification**

Run:

```powershell
python scripts/check_spec_compliance.py
git diff --check
```

Expected: both commands succeed with no authority, traceability, or whitespace errors.

- [ ] **Step 7: Commit**

```powershell
git add docs/superpowers/specs/2026-07-23-dow-realtime-watch-panel-design.md docs/superpowers/plans/2026-07-24-dow-monitor-card-chart-space.md docs/acceptance/2026-07-23-dow-realtime-watch-panel.md docs/reviews/2026-07-23-dow-realtime-watch-panel-review.md frontend/src/pages/DowMonitor.test.tsx frontend/src/components/dow-monitor/DowMonitorCard.tsx
git commit -m "fix: enlarge dow monitor mini charts"
```

