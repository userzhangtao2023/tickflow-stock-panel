# Dow Watch Overview Loading

## REQ-DOW-WATCH-OVERVIEW-LOAD-001

The Dow-monitor overview API MUST load the persisted timeframe-state collection
at most once per request. It MUST NOT deserialize the complete state collection
again for each monitored symbol or timeframe.

The bulk-read path MUST preserve the existing market filter, five-timeframe
state payloads, source timestamp, latest notification, runtime last-success
timestamp precedence, and persisted last-success fallback semantics.

For the current production monitor set, the authenticated Hong Kong and
all-market overview endpoints MUST complete within two seconds under the normal
production workload so that the page does not remain in its loading state.
