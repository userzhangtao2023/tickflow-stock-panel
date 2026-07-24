# Dow Watch Overview Loading Acceptance

Status: accepted

Requirements:

- `REQ-DOW-WATCH-OVERVIEW-LOAD-001`
- `REQ-DOW-WATCH-OVERVIEW-LOAD-002`

## Executable evidence

- The original behavioral test failed with 20 complete state-file reads for two
  symbols (10 reads per symbol). The bulk-load implementation reduced that to
  at most one read per overview request.
- The warm-snapshot regression test failed with two file reads for two
  `list_states()` calls. The in-process immutable snapshot implementation
  reduced that count to zero.
- The URL-market regression test failed because `?market=hk` invoked the
  overview hook with `all`; it now invokes overview and notification hooks with
  `hk` and selects the Hong Kong tab.
- `backend/tests/test_dow_monitor_api.py`: 18 passed.
- `frontend/src/pages/DowMonitor.test.tsx`: 33 passed.
- `tests/spec_contracts/test_dow_watch_overview_load_contract.py`: 2 passed.
- Specification compliance check: passed.
- Production frontend TypeScript and Vite build: passed.

## Production semantic evidence

- Fresh browser reload at
  `http://192.168.10.28:3018/dow-monitor?market=hk` selected `港股`, displayed
  exactly three articles (`01347.HK`, `0981.HK`, and `2714.HK`), and did not
  display `加载监控状态…`.
- Final authenticated steady-state measurements:
  status 13.8 ms, Hong Kong notifications 67.3 ms, Hong Kong overview 191.7 ms
  with three symbols, and all-market overview 623.4 ms with nine symbols.
- The real-time smoke test received a `TSLA.US` snapshot followed by an ordered
  update on the same stream (`sequence` 46778 then 46792).
- `longbridge-quote-subscription.service` and
  `longbridge-pg-realtime-backfill.service` were both active.

## Deployment and rollback

- Running image:
  `tickflow-stock-panel-app:dow-overview-load-v4-20260724-1835`
  (`sha256:ffffec9b3f24f0802182837c51518055c577c122e2465a6733451317791b3f2f`).
- Running container: `TickFlow_Stock_Panel`, status `running`, host network,
  restart policy `unless-stopped`, and the prior data/config mounts preserved.
- Rollback container:
  `TickFlow_Stock_Panel_pre_dow_overview_v4_20260724_1836`, image
  `tickflow-stock-panel-app:dow-overview-load-v3-20260724-1826`
  (`sha256:2c4ca1feb8313b48b4d5928e926ea0338cacbe8c5c1e265ea8a9fb9ee17c6cf8`).
