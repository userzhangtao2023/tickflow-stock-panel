# Dow monitor data integrity independent review

Date: 2026-07-24

The review traced both requirements from the authoritative specification to
implementation, executable tests, production storage, persisted states, and
the rendered page.

- `REQ-DOW-DATA-INTEGRITY-001`: the gateway now extends gap comparison to the
  requested end after the session has closed, while retaining the existing
  maximum-age rule during an active session. The unit test fails against the
  prior implementation and passes against the fix. ClickHouse then proves the
  repaired 330-minute lower-layer session, and the persisted state independently
  reports `LIVE` at 15:59.
- `REQ-DOW-MULTITIMEFRAME-WINDOW-001`: the frontend slices valid bars before
  constructing the x-axis, candlesticks, and visible signals. The behavioral
  test verifies the exact 80-bar boundary. Browser evidence confirms four
  distinct rendered canvases at the exact production URL.
- No frontend or downstream signal was used as a substitute for minute-layer
  acceptance; ClickHouse uniqueness and persisted freshness were checked
  first.
- The deployment preserves both the current built-in strategy layer and a
  named rollback container.

No Critical or Important requirement-to-evidence gap remains. The change does
not redefine Dow signal semantics or introduce a fallback live provider.
