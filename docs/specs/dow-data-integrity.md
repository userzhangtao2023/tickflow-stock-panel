# Dow monitor data integrity

## Authority

- Status: authoritative
- Approved by: user decision on 2026-07-24
- Requirements:
  - `REQ-DOW-DATA-INTEGRITY-001`
  - `REQ-DOW-MULTITIMEFRAME-WINDOW-001`

## REQ-DOW-DATA-INTEGRITY-001

The strict Dow monitor data gateway MUST classify a symbol as stale with
reason `SESSION_GAP` when an observed regular session has ended but the
persisted minute series does not reach the expected session close. Missing
tail minutes MUST be included in the reported gap details. During an active
session, the existing quote and minute maximum-age checks remain authoritative
for a missing live tail.

## REQ-DOW-MULTITIMEFRAME-WINDOW-001

Each Dow overview mini chart MUST render at most the most recent 80 valid bars
for its selected timeframe. The x-axis, candlesticks, and visible backend
signals MUST use the same bounded bar window. Backend trend and signal
semantics MUST NOT be recalculated or inferred by the frontend.
