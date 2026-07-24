# Dow monitor data integrity acceptance

Date: 2026-07-24

## Executable evidence

- `backend/tests/test_dow_monitor_data_integrity.py` proves the closed HK tail,
  whole-session zero-row, weekend cold-start, latest-prior-history, lunch
  segment, and US early-close behaviors against the exchange calendar.
- The focused backend suite, including the Dow monitor API regression tests,
  completed with `28 passed`.
- `backend/tests/test_dow_monitor_api.py` proves that a missing or invalid
  configuration is non-authoritative and that a persisted valid empty list is
  authoritative after deleting the final symbol.
- `frontend/src/pages/DowMonitor.test.tsx` proves that the x-axis,
  candlesticks, and signal markers share the latest 80-valid-bar window.
- The complete Dow monitor page suite completed with `34 passed`; the
  TypeScript and Vite production build also completed successfully.
- The three executable repository specification contracts passed.

## Production semantic evidence

On `192.168.10.28`:

- TickFlow runs image
  `tickflow-stock-panel-app:dow-data-integrity-completed-segments-ba3a913e-20260724`
  with `DATA_DIR=/app/data`; the immediate prior container is preserved as
  `TickFlow_Stock_Panel_pre_calendar_authority_20260724`.
- The loopback symbol endpoint reports `authoritative=true` with all 9 enabled
  monitor symbols. The Longbridge subscriber reports `healthy=true`,
  `monitor_symbol_count=9`, `symbol_count=348`, and `flush_failures=0`.
- ClickHouse contains exactly 330 unique regular-session minutes for
  `1347.HK` on 2026-07-24, from 09:30 through 15:59. The repair inserted 191
  missing keys with source `history_candlesticks_repair`; a second dry run
  reported zero missing rows.
- Persisted Dow states classify `01347.HK` as `LIVE` with source timestamp
  15:59. Its 5m/15m/30m/60m frames contain 924/308/154/84 bars and have four
  distinct content fingerprints:
  `619617d9bb2e0034`, `c4a4189793110dc9`,
  `4ede662d76a92ca9`, and `6c381598044b36fc`.
- The authenticated browser at
  `http://192.168.10.28:3018/dow-monitor?market=hk` rendered exactly the three
  HK cards, source time 16:00, and `01347.HK` at 149.80 with a successful
  19:57 refresh.
- Browser captures of the same `01347.HK` canvas at 5m/15m/30m/60m produced
  four distinct SHA-256 prefixes:
  `d3ea0d41930a4d8e`, `ebcb4a3d1213534b`,
  `2b917cbb3238f683`, and `7b8c30611fe14b52`.
