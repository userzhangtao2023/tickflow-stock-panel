# Task 8 report: Dow monitor frontend contracts and query hooks

## Scope

- Added exact frontend transport contracts for the Task 7 monitor API.
- Added the three market/timeframe query hooks, 15-second polling, preserved
  successful data during refreshes, and narrow mutation invalidations.
- Added no page, navigation, visual component, browser-time freshness logic, or
  local Dow-semantic calculation.

## RED/GREEN evidence

### RED

```powershell
cd frontend
pnpm test --run src/components/dow-monitor/useDowMonitor.test.tsx
```

Result: expected suite collection failure. Vite could not resolve
`./useDowMonitor` because the hook module did not exist.

### GREEN

The same command after implementation: `4 passed`.

The tests prove that market is sent only as the overview/notification query
parameter, detail sends only its `timeframe` query parameter, changing a query
retains the prior successful payload while the replacement is in flight, all
three read models use the 15-second polling contract, and mutations invalidate
only Dow-monitor query families.

## API/contract decisions

- Outer Task 7 persistence fields stay in their actual JSON form, including
  `source_timestamp`, `freshness_state`, `snapshot_payload`, and `read_at`.
- Engine fields retain their real mixed casing: `chart.longTerm`, line
  `anchorTimes`/`anchorPrices`, signal `barTime`, and `evaluatedAt`.
- Chinese `action_name`, `shape_name`, snapshot action values, notification
  activation fields, and the complete long-term sidecar are typed and passed
  through without local inference or translation.
- Query hooks use TanStack Query `keepPreviousData`; freshness therefore comes
  only from backend payload timestamps/states, not browser receipt time.
- The mutation hooks invalidate overview after symbol add/remove/enable changes;
  notification read invalidates notifications plus overview because the overview
  includes the latest persisted notification. Removing a symbol also evicts only
  that symbol's detail cache.

## Final verification

```powershell
cd frontend
pnpm test --run src/components/dow-monitor/useDowMonitor.test.tsx
pnpm test --run
pnpm build
git diff --check
cd ..
.\backend\.venv\Scripts\python.exe scripts\check_spec_compliance.py
```

Results: targeted hooks `4 passed`; complete frontend suite `59 passed` across
`22` files; TypeScript production build passed; whitespace check passed; the
repository specification checker passed.

`pnpm lint` could not run because the repository's lint script invokes `eslint`
but the checked-out frontend dependencies do not provide that executable. No
dependency/configuration change was made outside this task.

## Requirements mapping and independent review

The authoritative watch-design requirements remain deliberately unindexed under
`EXC-DOW-WATCH-IMPLEMENTATION-001`; its approved Task 12 promotion is still the
authority for `docs/traceability.yaml`. This task report supplies the required
task-level mapping without fabricating premature global acceptance evidence.

| Requirement | Implementation | Executable evidence | Independent semantic review |
| --- | --- | --- | --- |
| REQ-DOW-WATCH-FILTER-001 | `frontend/src/lib/api.ts`, `useDowMonitor.ts` | market-query test | The filter changes only GET query keys/parameters; no filter handler or enable mutation exists. |
| REQ-DOW-WATCH-UI-001 | `types.ts`, `useDowMonitor.ts` | hook polling/retention test | Types retain compact-card data, backend freshness fields, states, notification and source fields without browser-time inference. |
| REQ-DOW-WATCH-DETAIL-001 | `types.ts`, `api.ts` | detail URL test, production typecheck | The detail type passes through bars, lines, `anchorTimes`/`anchorPrices`, signals and `chart.longTerm`; it does not recompute them. |
| REQ-DOW-WATCH-SIGNAL-001 | `types.ts` | production typecheck | Snapshot, Chinese action/shape, line anchors and engine evidence retain backend casing/values. |
| REQ-DOW-WATCH-NOTIFY-001 | `types.ts`, `api.ts`, `useDowMonitor.ts` | mutation-invalidation test | Immutable `snapshot_payload`, activation snapshot and persisted `read_at` are typed unchanged; read invalidation refreshes persisted receipts. |
| REQ-DOW-WATCH-STALE-001 | `types.ts`, `useDowMonitor.ts` | production typecheck | `freshness_state` and `source_timestamp` are represented exactly and never derived locally. |
| REQ-DOW-WATCH-LONG-CLIENT-001 | `types.ts`, `api.ts` | production typecheck | Complete `chart.longTerm` and notification engine sidecars retain the Task 7 camel-case envelope and authoritative Chinese operation values. |

The independent review compared the frontend types with Task 7's actual
Pydantic models, service serializers, and endpoint tests. It specifically
checked that `current_ohlc` still includes `volume`, that external casing is not
normalised, and that stale/empty persisted states can omit chart arrays without
making the frontend invent a result.

## Files and commit

- `frontend/src/lib/api.ts`
- `frontend/src/lib/queryKeys.ts`
- `frontend/src/components/dow-monitor/types.ts`
- `frontend/src/components/dow-monitor/useDowMonitor.ts`
- `frontend/src/components/dow-monitor/useDowMonitor.test.tsx`
- `.superpowers/sdd/task-8-report.md`

Commit message: `feat: add dow monitor frontend api`.

## Concerns

1. `SPEC-DOW-WATCH-001` remains under the approved Task 12 traceability
   exception until promotion or 2026-08-06; this task does not alter that
   authority record.
2. Frontend lint is not executable in this checkout because `eslint` is absent;
   tests, typecheck/build, diff validation, and the specification checker pass.

## Review remediation

### Activation snapshot and legacy sidecar RED/GREEN

Added a typed persisted-response fixture with the backend activation shape
`{ active, family, structure_id, activation_sequence }`, a legacy
`chart.longTerm` containing only `trendDirection` and `operation`, and a legacy
notification engine containing only `snapshot`.

Before the type changes, `pnpm build` failed because `active` and
`trendDirection` were missing from the types and the partial engine snapshot was
forced to satisfy the full live-engine schema. After adding the exact activation
flag and compatibility-only partial sidecar types, the focused hook suite passed
`5` tests and `pnpm build` passed. The complete frontend suite then passed
`60` tests across `22` files.

The strict `DowMonitorEnginePayload` and `DowMonitorLongTermSnapshot` still
model the full live detail contract. Only persisted `chart.longTerm` and
notification `snapshot_payload.engine` use `Partial` known fields plus opaque
record compatibility, preserving their original casing and historical payloads.
