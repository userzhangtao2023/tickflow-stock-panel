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

---

## Review remediation addendum

The post-implementation review identified six important and three minor gaps.
This addendum supersedes the original concern that the card header had to derive
price/change from chart bars. The grid now consumes authoritative strict
realtime quote metadata supplied by the backend overview contract.

### Remediated behavior

- The ClickHouse strict realtime query joins the existing `lb_symbols` metadata
  table and returns its latest stored name. It does not invent a fallback name.
- The monitor service retains the latest successful strict quote per symbol and
  exposes `name`, `last_price`, `change_pct`, and `quote_timestamp` from that
  quote. A failed later poll retains those fields; chart bars are never used for
  the card header.
- The page polls `/api/dow-monitor/status` every 15 seconds. Loading, stopped,
  status/query failures, and unavailable status are visible and force every
  retained card and timeframe badge into a neutral blocked state. The page no
  longer claims that the backend is running or substitutes a hard-coded source.
- Add, remove, enable/disable, and mark-read failures remain visible and
  retryable. Pending controls are scoped to the affected record, and the add
  input clears only from the successful mutation callback.
- The card article is no longer an interactive surrogate. A dedicated,
  accessible detail button owns `onOpen(symbol, timeframe)`; keyboard activation
  of switches, remove controls, and timeframe controls cannot open details.
- Paused symbols render every timeframe and the summary as neutral/blocked,
  even when a persisted backend action or signal was formerly actionable.
- Runtime validation whitelists complete bars, `MAIN`/`ACCELERATION`
  `SUPPORT`/`RESISTANCE` lines, `BUY`/`SELL`/`RISK` signals whose coordinates
  reference a retained bar, and long-term lines with two complete valid
  anchors. Malformed legacy payloads are omitted safely without invented
  semantics.
- Each mini chart creates one ECharts instance, updates it with `setOption`,
  resizes through one `ResizeObserver`, and disconnects/disposes on unmount.
- The responsive `1 / 2 / 3 / 4` column classes remain intact, and retained
  loading/error layouts plus pending, malformed-legacy, and lifecycle states
  have executable coverage.

### Remediation RED/GREEN evidence

Backend RED tests first failed on the missing metadata join and missing overview
fields (`name`, `last_price`, `change_pct`, and `quote_timestamp`). Frontend RED
tests then failed on the absent status hook, chart-derived header, inaccessible
card activation, optimistic input clearing, missing mutation/query states,
non-neutral paused cards, unsafe legacy payload handling, and repeated ECharts
initialization.

Final GREEN commands and observed results:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_clickhouse_provider.py tests/test_dow_monitor_service.py tests/test_dow_monitor_api.py -q
# 81 passed

cd ..\frontend
pnpm test --run src/components/dow-monitor/useDowMonitor.test.tsx src/pages/DowMonitor.test.tsx
# 25 passed
pnpm test --run
# 80 passed across 23 files
pnpm build
# TypeScript and Vite build passed

cd ..
.\backend\.venv\Scripts\python.exe scripts\check_spec_compliance.py
# Specification compliance passed
```

The production build retains the repository's existing large-chunk warning.
The complete suite retains the existing React Router v7 future-flag warnings.

### Independent remediation requirements-to-evidence review

`SPEC-DOW-WATCH-001` remains authoritative under
`EXC-DOW-WATCH-IMPLEMENTATION-001`; this Task 9 remediation therefore records
task-level evidence without prematurely editing the final Task 12 traceability
index.

| Active requirement | Implementation evidence | Executable acceptance evidence | Review conclusion |
| --- | --- | --- | --- |
| `REQ-DOW-WATCH-UI-001` | `DowMonitor.tsx`, `DowMonitorCard.tsx`, `DowMonitorSignalRail.tsx` | authoritative header, responsive grid, status/error, mutation, pending and accessibility tests in `DowMonitor.test.tsx` | The grid uses strict quote headers, exposes truthful operational state, and has one dedicated detail control without adding a dialog or navigation. |
| `REQ-DOW-WATCH-FILTER-001` | `DowMonitor.tsx` | shared market/signal filter and no-toggle-on-market-change tests | One local market value still gates cards and notifications, with no monitoring mutation from filter changes. |
| `REQ-DOW-WATCH-DATA-001` | `provider.py`, `dow_monitor_service.py`, `types.ts` | strict metadata join, retained quote, API contract and no-chart-derivation tests | Header data originates in the strict realtime quote path; later query failure retains the latest successful quote and does not invoke a fallback source. |
| `REQ-DOW-WATCH-MTF-001` | `DowMonitorCard.tsx` | five-timeframe selection, paused-all-neutral and query-blocked-all-neutral tests | Timeframe controls remain per-card display state; disabled or operationally blocked cards cannot present actionable colors. |
| `REQ-DOW-WATCH-SIGNAL-001` | `DowMiniChart.tsx`, `DowMonitorCard.tsx` | exact line/signal colors, empty-array, adversarial payload and lifecycle tests | The UI accepts only whitelisted complete backend semantics. Unknown or malformed records disappear rather than being coerced into a known signal/line. |
| `REQ-DOW-WATCH-NOTIFY-001` | `DowMonitorSignalRail.tsx`, `DowMonitor.tsx` | loading/error, read-failure/retry and scoped read-pending tests | Persisted notifications remain bounded and visible; read state is explicit and retryable. |
| `REQ-DOW-WATCH-BACKGROUND-001` | `useDowMonitor.ts`, `DowMonitor.tsx` | 15-second status-query and stopped/loading/error retained-layout tests | The page reports backend status from the status endpoint and never hard-codes a running claim. |
| `REQ-DOW-WATCH-STALE-001` | `DowMonitorCard.tsx`, `DowMonitor.tsx` | freshness, paused, stopped, query-loading and query-error blocking tests | Lower-layer freshness and operational availability are semantic gates; retained data never substitutes for a live/tradable claim. |

Lower-layer DOW line, signal, and long-term acceptance remains the semantic
authority. These higher-layer tests establish faithful consumption and safe
rejection only; no passing UI snapshot or color assertion is treated as proof
of lower-layer semantics.

### Additional remediation files

- `backend/app/plugins/clickhouse/provider.py`
- `backend/app/services/dow_monitor_service.py`
- `backend/tests/test_clickhouse_provider.py`
- `backend/tests/test_dow_monitor_service.py`
- `backend/tests/test_dow_monitor_api.py`
- `frontend/src/components/dow-monitor/types.ts`
- `frontend/src/components/dow-monitor/useDowMonitor.ts`
- `frontend/src/components/dow-monitor/useDowMonitor.test.tsx`
- `frontend/src/lib/queryKeys.ts`

---

## Second review remediation addendum

The second review found two important concurrency/readiness gaps and two minor
truthfulness/visibility gaps. This pass changes frontend consumers only; the
existing status and overview contracts already contain every required server
field.

### Readiness and visible server freshness

- `running=true` no longer unlocks retained cards by itself. The status query
  must be present, non-loading, non-error, running, and contain both
  `last_completed_at` and `last_success_at`.
- A restarted backend that has not completed one successful cycle shows
  `后台准备中` plus `等待后台首轮监控结果`. Retained cards and every timeframe
  remain neutral/blocked, and retained price/change are replaced by `—`.
- Once both cycle timestamps arrive, each card is again eligible according to
  its own backend `freshness_state`, enabled state, and per-symbol state.
  A populated status `last_error` does not globally block otherwise ready
  symbols when a successful completed cycle exists.
- Loading, failed, absent, stopped, preparing, and running status labels are
  mutually consistent. In particular, failed and absent queries show
  `后台连接失败` and `后台状态未知`, never a retained running/stopped claim.
- The sighted UI now renders compact UTC labels directly from server fields:
  card `quote_timestamp`, card `last_success_at`, and overview
  `source_timestamp`. Formatting is deterministic and never compares against
  browser current time.

### Concurrent mutation ownership

Toggle, remove, and mark-read operations now use component-owned pending sets
and error sets/maps keyed by symbol or notification ID. Each call awaits its
own `mutateAsync` Promise, so a later mutation cannot replace the completion
observer for an earlier mutation.

Executable tests start A then B and settle them in reverse order for all three
mutation families. They prove:

- both records can be pending concurrently;
- B can settle and re-enable without re-enabling unresolved A;
- a B failure stays visible after A later succeeds;
- failures identify the affected record and remain retryable;
- an add request still owns only its single input/button and does not serialize
  unrelated stock controls.

### Second-pass RED/GREEN evidence

The expanded focused suite first reported 8 failures out of 24. Failures
directly covered the missing first-cycle readiness gate, contradictory status
label, hidden server timestamps, missing per-call mutation settlement API, and
non-independent pending controls.

Final observed commands:

```powershell
cd frontend
pnpm test --run src/pages/DowMonitor.test.tsx
# 24 passed

pnpm test --run
# 85 passed across 23 files

pnpm build
# TypeScript and Vite build passed

cd ..
.\backend\.venv\Scripts\python.exe scripts\check_spec_compliance.py
# Specification compliance passed

git diff --check
# passed
```

The production build retains the existing large-chunk warning. The complete
suite retains the existing React Router v7 future-flag warnings.

### Independent second-pass requirements-to-evidence review

| Active requirement | Implementation evidence | Executable evidence | Review conclusion |
| --- | --- | --- | --- |
| `REQ-DOW-WATCH-UI-001` | `DowMonitor.tsx`, `DowMonitorCard.tsx`, `formatServerTimestamp.ts` | restart-not-ready, status-label and exact visible timestamp assertions | Retained data cannot present a live quote/action header before the new backend process has completed a successful cycle; all displayed freshness times originate from the server. |
| `REQ-DOW-WATCH-BACKGROUND-001` | `DowMonitor.tsx` | running-with-null-cycle versus completed-success rerender test | Runtime readiness requires an observed successful completed cycle, not the process task's running flag alone. |
| `REQ-DOW-WATCH-STALE-001` | `DowMonitor.tsx`, `DowMonitorCard.tsx` | global first-cycle blocking followed by per-state eligibility test | The frontend adds only an operational readiness gate. It does not calculate freshness from browser time or override lower-layer per-symbol freshness states. |
| `REQ-DOW-WATCH-FILTER-001` / mutation isolation | `DowMonitor.tsx`, `DowMonitorSignalRail.tsx` | reverse-settlement toggle, removal and read tests | Pending and failure state is keyed by the affected record and backed by each call's own Promise; unrelated stocks remain independently actionable. |

The reviewed diff contains no backend, detail-dialog, navigation, scheduling, or
lower-layer DOW semantic changes.
