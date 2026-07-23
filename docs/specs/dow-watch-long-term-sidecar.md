# Dow watch long-term sidecar bridge

## Authority and scope

`SPEC-DOW-WATCH-LONG-001` records the approved lower-layer bridge needed by
`SPEC-DOW-WATCH-001`. The approval is recorded in
`docs/decisions/2026-07-23-dow-watch-long-term-sidecar.md`.

This specification is a consumer contract only. `DOW-LONG-001` defines all
long-horizon semantics and `SPEC-DOW-EXTERNAL-STATE-001` defines their external
serialization. Those lower-layer contracts prevail. TickFlow may validate,
persist, display, and activate their output but must not recompute or
reinterpret it.

## Active requirements

- **REQ-DOW-WATCH-LONG-CLIENT-001:** TickFlow MUST strictly validate the
  complete `longTerm` sidecar, including strict booleans, authoritative
  completion/stage/trend/breakout/operation enums, `PRIMARY`-only recent-low
  scale, and strict ISO date/datetime strings that reject numeric coercion; it
  MUST preserve the sidecar and its string timestamp representation in public
  persisted timeframe state and chart payload without changing the existing
  local snapshot, lines, signals, actions, or activation semantics.
  User-facing names and evidence codes remain lower-layer free text.
- **REQ-DOW-WATCH-LONG-EVENT-001:** TickFlow MUST emit an independent
  long-term event only for lower-layer `买入触发` or `卖出触发` with
  `bar_completion == FINAL`, `provisional == false`, a non-empty
  whitespace-trimmed line ID, and `signal_stage` equal to `TRIGGER` or
  `CONFIRMED`; long-term families MUST remain distinct from local families
  while retaining the five-part event key.
- **REQ-DOW-WATCH-LONG-RECOVERY-001:** Local and long-term activations MUST
  deduplicate, deactivate/reactivate, sequence, and recover both first-state
  and existing-state notification-written/state-write-crash windows
  independently through public state and immutable notification history.

## Acceptance order

1. Validate lower-layer `DOW-EXTERNAL-105` semantic acceptance.
2. Prove strict typed parsing and complete sidecar persistence.
3. Prove simultaneous local and long-term activations produce independent
   sequence-one event keys.
4. Prove forming/provisional candidates are display-only.
5. Prove sustained dedupe, reactivation sequence increment, and both
   first-state and existing-state notification-written/state-not-written crash
   recovery for the long-term family.
