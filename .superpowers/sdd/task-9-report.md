# Task 9 report: compact Dow monitor grid and signal rail

## Scope

- Added the compact multi-stock monitor page shell without App navigation or the
  Task 10 detail dialog.
- Added a fixed, bounded latest-signal rail; synchronized market and signal
  filters; independent per-symbol switches; Task 8 add/remove mutations; and a
  responsive four-column wide-screen card grid.
- Added five always-visible per-card timeframe controls. Selecting one changes
  only that card's mini chart; card activation emits `onOpen(symbol,
  timeframe)` for Task 10.
- Added a minimal ECharts candlestick overlay that consumes only backend bars,
  lines, signals, and complete persisted long-term anchors.

## Specification authority

`SPEC-DOW-WATCH-001` is the authoritative UI design. Its exact-specification
exception `EXC-DOW-WATCH-IMPLEMENTATION-001` remains complete and unexpired
through 2026-08-06, so the approved Task 12 promotion remains the authority for
global requirement indexing. `SPEC-DOW-WATCH-LONG-001` supplements it without
changing the lower-layer authority of `DOW-LONG-001` and
`SPEC-DOW-EXTERNAL-STATE-001`.

The lower-layer long-term acceptance and independent review were checked before
the UI implementation. They establish that `chart.longTerm` is validated and
persisted unchanged; this task only displays two complete authoritative anchors
and never constructs an anchor, trend, stage, line, or signal.

## RED/GREEN evidence

### RED

```powershell
cd frontend
pnpm test --run src/pages/DowMonitor.test.tsx
```

Result: expected suite collection failure. Vite could not resolve
`./DowMonitor` because the Task 9 page and components did not exist.

### GREEN

The same command after implementation passed all 11 Task 9 tests. The suite
exercises:

- wide-screen `2xl:grid-cols-4`;
- one market value filtering cards and notifications;
- all/active/buy/sell signal filtering;
- no enable mutation from a market tab;
- independent symbol switches;
- Task 8 add/remove mutations;
- five always-visible timeframe controls and per-card-only selection;
- Task 10 `onOpen(symbol, timeframe)` emission;
- buy green, sell/risk red, watch amber, none gray, and stale/paused blocking;
- the compact no-signal state;
- hidden axes and legend-free mini charts;
- solid main and dashed acceleration line styles;
- green backend BUY markers and red backend SELL/RISK markers;
- amber long-term rendering only when both persisted times and prices exist;
- no inferred line or marker when backend arrays are empty.

## Implementation decisions

- The page passes the selected market to the Task 8 overview/notification hooks
  and also applies the same market locally. The local gate prevents
  `keepPreviousData` from momentarily showing the previous market while the new
  query is in flight. Market handlers never reference the enable mutation.
- The fixed signal rail displays at most eight already-filtered latest records
  in a non-carousel grid, preserving backend order and the backend Chinese
  action/shape text.
- Signal filters use only persisted `latest_notification.side`. Card timeframe
  colors use only backend signal side or backend snapshot `action_code`; they do
  not synthesize a chart marker or notification.
- Paused symbols and backend `STALE_DATA` / `ANALYSIS_PAUSED` states expose
  `data-tradable="false"` and muted blocked styling. A blocked selected state
  replaces historical trade wording with the backend block reason.
- Candlesticks reuse TickFlow's red-up/green-down convention. Trade actions use
  the user-approved independent semantics: BUY green, SELL/RISK red, WATCH
  amber, and none gray.
- Main support/resistance lines are solid blue/magenta. Acceleration variants
  are dashed. The optional long-term line is amber and exists only when all four
  persisted anchor fields are complete and numeric.

## Final verification

```powershell
cd frontend
pnpm test --run src/pages/DowMonitor.test.tsx
pnpm test --run
pnpm build
pnpm lint
cd ..
git diff --check
.\backend\.venv\Scripts\python.exe scripts\check_spec_compliance.py
```

Observed results before the final commit:

- focused Task 9 suite: 11 passed;
- complete frontend suite: 71 passed across 23 files;
- TypeScript/Vite production build: passed;
- lint: unavailable because the repository script invokes `eslint`, but the
  checked-out frontend dependencies do not provide that executable;
- the remaining whitespace and specification checks are repeated after this
  report is written.

The build retains the repository's existing Vite chunk-size warning. The full
suite retains its existing React Router v7 future-flag warnings.

## Independent requirements-to-evidence review

The authoritative watch requirements remain deliberately unindexed under the
approved Task 12 exception. This task-level review records concrete evidence
without prematurely changing `docs/traceability.yaml`.

| Requirement | Implementation | Executable evidence | Independent semantic review |
| --- | --- | --- | --- |
| `REQ-DOW-WATCH-UI-001` | `DowMonitor.tsx`, `DowMonitorCard.tsx`, `DowMiniChart.tsx`, `DowMonitorSignalRail.tsx` | grid, five-timeframe, colors, no-signal and chart tests | Cards are compact, four columns on wide screens, K-line-primary, and contain no axes, legends, indicator panels, carousel, or explanatory prose. |
| `REQ-DOW-WATCH-FILTER-001` | `DowMonitor.tsx` | synchronized market/signal filter tests and no-mutation test | One local market value gates both read models; only the switch handler calls the enable mutation. |
| `REQ-DOW-WATCH-MTF-001` | `DowMonitorCard.tsx` | five badges and per-card-only timeframe selection test | Selection is local card display state and never changes backend monitoring or another card. |
| `REQ-DOW-WATCH-SIGNAL-001` | `DowMiniChart.tsx`, `DowMonitorCard.tsx`, `DowMonitorSignalRail.tsx` | marker/color, fixed rail and no-inference tests | Markers and notification text come only from returned backend signals/notifications; empty arrays stay empty. |
| `REQ-DOW-WATCH-STALE-001` | `DowMonitorCard.tsx` | stale/analysis-paused blocked appearance test | Backend freshness state blocks tradable presentation; browser time never determines freshness. |
| approved long-term amber-line addendum | `DowMiniChart.tsx` | complete/incomplete persisted-anchor test | Both authoritative anchor times and prices are required; missing fields produce no line and no inferred substitute. |

## Files

- `frontend/src/components/dow-monitor/DowMiniChart.tsx`
- `frontend/src/components/dow-monitor/DowMonitorCard.tsx`
- `frontend/src/components/dow-monitor/DowMonitorSignalRail.tsx`
- `frontend/src/pages/DowMonitor.tsx`
- `frontend/src/pages/DowMonitor.test.tsx`
- `.superpowers/sdd/task-9-report.md`

## Concerns and preserved boundaries

1. The Task 8/backend overview contract has no stock-name field. Task 9 shows
   symbol plus current price/change derived from returned bars, but cannot
   truthfully show a display name. A future backend contract change must supply
   that field; this task does not fabricate one.
2. The page is intentionally not registered in App navigation, and no detail
   dialog is added. Task 10 can pass its dialog opener to the implemented
   `onOpen(symbol, timeframe)` seam.
3. Frontend lint remains unavailable because `eslint` is not installed in the
   checked-out dependency graph. No dependency/configuration change was made
   outside Task 9.
