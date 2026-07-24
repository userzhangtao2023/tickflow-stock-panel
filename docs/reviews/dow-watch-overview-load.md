# Dow Watch Overview Loading Independent Review

Status: accepted

Requirements reviewed:

- `REQ-DOW-WATCH-OVERVIEW-LOAD-001`
- `REQ-DOW-WATCH-OVERVIEW-LOAD-002`

## Requirements-to-evidence review

- The service constructs one symbol/timeframe index from `list_states()` and
  reuses those states for payload assembly and persisted last-success fallback.
  It no longer calls `get_state()` once per timeframe.
- The store loads the persisted state collection once during initialization.
  `list_states()` and `get_state()` use an immutable tuple snapshot. State saves
  and symbol removals write through atomic file replacement before publishing a
  replacement tuple, so readers see a complete old-or-new snapshot without
  waiting for the writer lock.
- The backend regression tests independently cover read count, lock-free
  snapshot access, five-timeframe payload preservation, market filtering,
  timestamps, notifications, and detail behavior. The full API suite passed;
  no downstream screenshot or golden file was used as semantic proof.
- The page initializes its market state from the supported URL values and falls
  back to `all` for invalid or absent values. The focused frontend test proves
  that `?market=hk` drives the initial overview and notification requests.
- The production API returned the expected three Hong Kong and nine total
  symbols within the two-second steady-state budget. A fresh browser reload,
  rather than a cached screenshot, confirmed that the exact user URL selected
  Hong Kong, rendered three stock cards, and exited the loading state.
- The deployed image is a derivative of the prior production image: the
  frontend layer contains only the URL-market change and the backend layer
  contains only the tested state-cache change. Real-time ordered-stream
  evidence and active Longbridge services show the lower data-acquisition layer
  remained accepted.

Conclusion: both requirements are traced to implementation, executable tests,
production timing, fresh-page semantic evidence, and an explicit rollback
identity. No unresolved specification conflict remains.
