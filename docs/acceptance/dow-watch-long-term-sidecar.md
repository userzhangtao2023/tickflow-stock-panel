# Semantic acceptance: Dow watch long-term sidecar

The lower-layer acceptance for `DOW-EXTERNAL-105` was checked first: the same
visible bars and completion reach `LongHorizonDowAnalyzer`, all snapshot fields
are serialized, local results are unchanged, and FORMING remains provisional.

- **REQ-DOW-WATCH-LONG-CLIENT-001:** Accepted. The typed client rejects extra
  sidecar fields, exposes every field, and maps schema failures to
  `DowEngineUnavailable`. The service persists the complete object under
  `chart.longTerm` while retaining local `snapshot`, `lines`, and `signals`.
- **REQ-DOW-WATCH-LONG-EVENT-001:** Accepted. Controlled simultaneous local
  and long-term FINAL triggers produce `OPEN_LONG` and `LONG_TERM_BUY`
  sequence-one keys. A controlled FORMING trigger remains visible and emits
  no notification.
- **REQ-DOW-WATCH-LONG-RECOVERY-001:** Accepted. Controlled sustained
  long-term output emits once, inactive then active output emits sequence two,
  and a simulated first state-write crash recovers the existing sequence-one
  activation from immutable public notification history.

This acceptance uses executable structured assertions, not a snapshot,
golden, screenshot, or downstream UI result.
