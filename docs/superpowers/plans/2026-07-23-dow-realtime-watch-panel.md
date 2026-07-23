# Dow Realtime Watch Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 TickFlow 现有框架中增加一个 WebStock 优先、后台常驻、同时监控 A 股/港股/美股与 5m/15m/30m/60m/日线的道氏多股票监控页面，并按形成中 K 线的当时形态生成不可变的页面通知。

**Architecture:** TickFlow 通过现有 `clickhouse` 自定义数据源读取 WebStock 采集的实时行情和标准化 1 分钟 K 线，严格检查交易时段、连续性和新鲜度后聚合五个周期；TickFlow 不复制道氏算法，而把标准化 K 线提交给 `longbridge-stock` 的新增“外部 K 线求值”接口。后台监控服务维护每只股票、每个周期的当前状态与事件激活序列，持久化不可变通知；React 页面只查询状态、过滤卡片/通知并复用现有 K 线和指标控件。

**Tech Stack:** Python 3.11、FastAPI、Pydantic 2、Polars、httpx、pytest；React 18、TypeScript、TanStack Query、ECharts、Tailwind CSS、Vitest/Testing Library；Chronicle 仅用于部署后的健康巡检。

## Global Constraints

- 权威设计：`docs/superpowers/specs/2026-07-23-dow-realtime-watch-panel-design.md`。
- 活跃需求 ID：`REQ-DOW-WATCH-UI-001`、`REQ-DOW-WATCH-DETAIL-001`、`REQ-DOW-WATCH-FILTER-001`、`REQ-DOW-WATCH-DATA-001`、`REQ-DOW-WATCH-MTF-001`、`REQ-DOW-WATCH-SIGNAL-001`、`REQ-DOW-WATCH-NOTIFY-001`、`REQ-DOW-WATCH-BACKGROUND-001`、`REQ-DOW-WATCH-STALE-001`、`REQ-DOW-WATCH-MARKET-001`。
- 道氏线段、锚点、形成中 K 线、动作和三市场交易时段的下层权威仍是 `longbridge-stock` 的 `DOW-LINE-001`、`DOW-AUTO-001`、`DOW-CAUSAL-001`、`DOW-ACTION-001`、`DOW-BAR-001`、`DOW-MTF-001`、`DOW-MKT-001`、`DOW-WINDOW-001`、`DOW-LONG-001`；TickFlow 不得重写这些语义。
- 开始上层实现前，必须先运行 `longbridge-stock/scripts/check_spec_compliance.py`，并核对对应 executable test、semantic acceptance、independent review；截图和 TickFlow 测试不能替代下层语义验收。
- 所有行为变更先写失败测试，再写最小实现；每一项提交只包含该项文件，不得夹带两个工作区现有的脏文件。
- 监控数据源固定优先使用 TickFlow 已注册的 `clickhouse` 内置数据源（其中 `lb_realtime_quotes`、`lb_minute_bars`、`lb_intraday_lines` 来自 WebStock 采集链路）；监控路径禁止调用该 provider 的 Longbridge API fallback。
- 盘中实时行情超过 90 秒、最新 1 分钟 K 超过 120 秒，或正常交易时段中间出现未解释的 1 分钟缺口时，状态进入 `STALE_DATA`，保留最后可靠状态并停止产生新通知。
- 市场时段必须来自下层 `DOW-MKT-001`：A 股 09:30–11:30/13:00–15:00（Asia/Shanghai），港股 09:30–12:00/13:00–16:00（Asia/Hong_Kong），美股常规时段 09:30–16:00（America/New_York）；午休、休市和盘后数据不聚合进常规 K 线。
- 监控轮询默认 15 秒；页面是否打开不得影响轮询。Chronicle 只做 10 分钟一次的健康巡检，不增加 systemd 服务。
- 通知事件键固定为 `symbol + timeframe + signal_family + structure_id + activation_sequence`；同一持续事件只通知一次，解除后重新触发必须递增 `activation_sequence`。
- 第一轮语义验收只使用 `01347.HK`。用户确认后，才各增加一只 A 股和美股做市场时段验收；在这之前不得批量测试或扩散到全市场。
- 第一阶段不自动下单，不发送飞书、QQ、短信或邮件。
- 页面顶部市场筛选固定为 `ALL / A股 / 港股 / 美股`；它只过滤卡片和通知，不得改变后台监控开关。

---

### Task 1: Establish the lower-layer external-bar evaluation contract

**Files:**
- Create: `../longbridge-stock/.worktrees/universal-intraday-dow-fingerprint/docs/specs/dow-external-bar-evaluation.md`
- Create: `../longbridge-stock/.worktrees/universal-intraday-dow-fingerprint/docs/decisions/2026-07-23-dow-external-bar-evaluation.md`
- Modify: `../longbridge-stock/.worktrees/universal-intraday-dow-fingerprint/docs/spec-index.yaml`
- Modify: `../longbridge-stock/.worktrees/universal-intraday-dow-fingerprint/docs/traceability.yaml`
- Create: `../longbridge-stock/.worktrees/universal-intraday-dow-fingerprint/tests/fixtures/dow/01347_hk_external_30m.json`
- Create: `../longbridge-stock/.worktrees/universal-intraday-dow-fingerprint/tests/test_dow_external_state.py`
- Create: `../longbridge-stock/.worktrees/universal-intraday-dow-fingerprint/src/longbridge_stock/dow_external_state.py`
- Modify: `../longbridge-stock/.worktrees/universal-intraday-dow-fingerprint/src/longbridge_stock/api.py`
- Create: `../longbridge-stock/.worktrees/universal-intraday-dow-fingerprint/docs/acceptance/2026-07-23-dow-external-bar-evaluation.md`
- Create: `../longbridge-stock/.worktrees/universal-intraday-dow-fingerprint/docs/reviews/2026-07-23-dow-external-bar-evaluation-review.md`

**Interfaces:**
- Consumes: `DowTrendReplayEngine.replay(rows)`, `context_from_replay(...)`, `DowBarStateClassifier.classify(...)`, `serialize_bar_state(...)`.
- Produces: `evaluate_external_bars(request: ExternalDowRequest) -> dict[str, object]`.
- Produces HTTP: `POST /api/dow-state/evaluate`.
- Request:

```json
{
  "symbol": "01347.HK",
  "timeframe": "30m",
  "completion": "FORMING",
  "asOf": "2026-07-23T10:47:15+08:00",
  "bars": [
    {
      "timestamp": "2026-07-23T09:30:00+08:00",
      "open": 1.23,
      "high": 1.25,
      "low": 1.22,
      "close": 1.24,
      "volume": 900000
    }
  ]
}
```

- Response keys: `symbol`, `timeframe`, `snapshot`, `bars`, `lines`, `signals`, `evaluatedAt`; each line contains `id`, `side`, `role`, `generation`, `anchorIndexes`, `anchorTimes`, `anchorPrices`, `createdIndex`, `invalidatedIndex`, `controlsSignals`.

- [ ] **Step 1: Register the adapter-only authority with a bounded implementation exception**

Add `SPEC-DOW-EXTERNAL-STATE-001` with requirements `DOW-EXTERNAL-101` through `DOW-EXTERNAL-104`. The spec must say:

```markdown
- DOW-EXTERNAL-101: The endpoint MUST evaluate caller-supplied normalized bars without fetching market data.
- DOW-EXTERNAL-102: It MUST use the existing replay and bar-state engines without alternate line or signal rules.
- DOW-EXTERNAL-103: FORMING MUST treat the last input bar as forming and all preceding bars as completed.
- DOW-EXTERNAL-104: The response MUST preserve line IDs, roles, anchors, signals, Chinese phase/action, and bar completion.
```

Record the user-approved cross-project adapter decision in
`docs/decisions/2026-07-23-dow-external-bar-evaluation.md`. Register the new
specification as authoritative with an empty indexed requirement list and this
temporary exact-specification exception:

```yaml
- id: EXC-DOW-EXTERNAL-IMPLEMENTATION-001
  scope: SPEC-DOW-EXTERNAL-STATE-001
  owner: alwinzhang
  reason: The approved external-bar adapter is being implemented and its executable evidence is created in this task.
  approval: docs/decisions/2026-07-23-dow-external-bar-evaluation.md
  expires: 2026-08-06
```

Run:

```powershell
cd E:\my_project\longbridge-stock\.worktrees\universal-intraday-dow-fingerprint
python scripts/check_spec_compliance.py
```

Expected: PASS under the bounded exact-specification implementation exception; all pre-existing specifications remain resolved.

- [ ] **Step 2: Write the failing pure-function and API tests**

```python
def test_external_forming_bar_uses_existing_engine_and_preserves_anchors(fixture_rows):
    result = evaluate_external_bars(ExternalDowRequest(
        symbol="01347.HK",
        timeframe="30m",
        completion="FORMING",
        as_of=datetime.fromisoformat("2026-07-23T10:47:15+08:00"),
        bars=fixture_rows,
    ))
    assert result["snapshot"]["bar_completion"] == "FORMING"
    assert result["snapshot"]["phase"]
    assert all(len(line["anchorTimes"]) == 2 for line in result["lines"])
    assert {line["role"] for line in result["lines"]} >= {"MAIN"}


def test_external_endpoint_does_not_call_sdk(monkeypatch, fixture_payload):
    monkeypatch.setattr(
        "longbridge_stock.sdk_client.LongbridgeSdkClient.kline_no_adjust",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SDK must not run")),
    )
    response = TestClient(app).post("/api/dow-state/evaluate", json=fixture_payload)
    assert response.status_code == 200
```

Run:

```powershell
python -m pytest tests/test_dow_external_state.py -q
```

Expected: FAIL because `dow_external_state` and `/api/dow-state/evaluate` do not exist.

- [ ] **Step 3: Implement the row adapter without copying Dow rules**

```python
@dataclass(frozen=True)
class ExternalDowRequest:
    symbol: str
    timeframe: str
    completion: Literal["FORMING", "FINAL"]
    as_of: datetime
    bars: tuple[Mapping[str, object], ...]


def evaluate_external_bars(request: ExternalDowRequest) -> dict[str, object]:
    if request.timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"unsupported timeframe: {request.timeframe}")
    if len(request.bars) < 3:
        raise ValueError("at least three bars are required")
    replay_rows = request.bars[:-1] if request.completion == "FORMING" else request.bars
    replay = DowTrendReplayEngine().replay(replay_rows)
    forming = (
        Bar.from_mapping(len(replay_rows), request.bars[-1])
        if request.completion == "FORMING"
        else None
    )
    context = context_from_replay(
        replay,
        symbol=request.symbol,
        timeframe=request.timeframe,
        completion=request.completion,
        forming_bar=forming,
    )
    snapshot = DowBarStateClassifier().classify(context)
    visible = replay.bars + ((forming,) if forming is not None else ())
    time_by_index = {bar.index: bar.timestamp for bar in visible}
    return {
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "snapshot": serialize_bar_state(snapshot),
        "bars": [_serialize_bar(bar) for bar in visible],
        "lines": [_serialize_line(line, time_by_index) for line in replay.lines],
        "signals": [_serialize_signal(signal, time_by_index) for signal in replay.signals],
        "evaluatedAt": request.as_of.isoformat(),
    }
```

The API handler parses camel-case JSON into `ExternalDowRequest`, maps `ValueError` to HTTP 400, and returns the pure function result.

- [ ] **Step 4: Complete traceability, remove the exception, and verify lower-layer semantics**

Change the indexed requirement list to all four `DOW-EXTERNAL-*` IDs, add their
real implementation/test/acceptance/review paths to `docs/traceability.yaml`,
and remove `EXC-DOW-EXTERNAL-IMPLEMENTATION-001`.

Run:

```powershell
python -m pytest tests/test_dow_external_state.py tests/test_dow_bar_state.py tests/test_dow_multitimeframe_state.py tests/test_dow_multimarket_state.py -q
python scripts/check_spec_compliance.py
```

Expected: all selected tests PASS and the specification checker exits 0.

Record in semantic acceptance the exact 01347 fixture time, expected active line IDs, two anchor times, phase/action and forming-bar status. The independent review must compare the fixture response to the applicable lower-layer requirement IDs, not to a screenshot.

- [ ] **Step 5: Commit the lower-layer adapter**

```powershell
git add docs/specs/dow-external-bar-evaluation.md docs/decisions/2026-07-23-dow-external-bar-evaluation.md docs/spec-index.yaml docs/traceability.yaml tests/fixtures/dow/01347_hk_external_30m.json tests/test_dow_external_state.py src/longbridge_stock/dow_external_state.py src/longbridge_stock/api.py docs/acceptance/2026-07-23-dow-external-bar-evaluation.md docs/reviews/2026-07-23-dow-external-bar-evaluation-review.md
git commit -m "feat: evaluate external bars with dow engine"
```

---

### Task 2: Persist monitored symbols, timeframe states, and immutable notifications

**Files:**
- Create: `docs/decisions/2026-07-23-dow-realtime-watch-panel.md`
- Modify: `docs/superpowers/specs/2026-07-23-dow-realtime-watch-panel-design.md`
- Modify: `docs/spec-index.yaml`
- Create: `backend/app/services/dow_monitor_models.py`
- Create: `backend/app/services/dow_monitor_store.py`
- Create: `backend/tests/test_dow_monitor_store.py`

**Interfaces:**
- Produces: `DowMonitorStore(data_dir: Path)`.
- Produces: `list_symbols()`, `upsert_symbol(symbol, market, enabled)`, `remove_symbol(symbol)`, `save_state(state)`, `get_state(symbol, timeframe)`, `append_notification(notification)`, `list_notifications(market=None, unread_only=False, limit=100)`, `mark_read(notification_id)`.
- Storage files: `data/user_data/dow_monitor_symbols.json`, `dow_monitor_states.json`, `dow_monitor_notifications.jsonl`, `dow_monitor_activations.json`.

- [ ] **Step 1: Register approved authority with a bounded implementation exception**

Record the user's approval in
`docs/decisions/2026-07-23-dow-realtime-watch-panel.md`, change the design
status to `已批准，实施中`, and register `SPEC-DOW-WATCH-001` as authoritative
with an empty indexed requirement list plus:

```yaml
- id: EXC-DOW-WATCH-IMPLEMENTATION-001
  scope: SPEC-DOW-WATCH-001
  owner: alwinzhang
  reason: The approved watch-panel requirements are being implemented and executable evidence is created by this plan.
  approval: docs/decisions/2026-07-23-dow-realtime-watch-panel.md
  expires: 2026-08-06
```

Run:

```powershell
cd E:\my_project\tickflow-stock-panel
python scripts/check_spec_compliance.py
```

Expected: PASS under the bounded exact-specification implementation exception.

- [ ] **Step 2: Write failing persistence tests**

```python
def test_store_persists_switches_and_immutable_notifications(tmp_path):
    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", enabled=True)
    first = notification(event_key="01347.HK|30m|OPEN_LONG|LINE-7|1", price=1.23)
    store.append_notification(first)
    changed = {**first.model_dump(), "trigger_price": 9.99}
    assert store.append_notification(DowNotification.model_validate(changed)) is False

    restored = DowMonitorStore(tmp_path)
    assert restored.list_symbols()[0].enabled is True
    assert restored.list_notifications()[0].trigger_price == 1.23
```

Also cover atomic JSON replacement, malformed trailing JSONL lines, read status and removal of a symbol without deleting its historical notifications.

Run:

```powershell
cd E:\my_project\tickflow-stock-panel\backend
python -m pytest tests/test_dow_monitor_store.py -q
```

Expected: FAIL because the store and models do not exist.

- [ ] **Step 3: Define typed persisted records**

```python
class MonitoredSymbol(BaseModel):
    symbol: str
    market: Literal["cn", "hk", "us"]
    enabled: bool = True
    created_at: datetime
    updated_at: datetime


class DowTimeframeState(BaseModel):
    symbol: str
    market: Literal["cn", "hk", "us"]
    timeframe: Literal["5m", "15m", "30m", "60m", "day"]
    freshness_state: Literal["LIVE", "STALE_DATA", "ANALYSIS_PAUSED"]
    source_timestamp: datetime | None
    snapshot: dict
    chart: dict
    updated_at: datetime


class DowNotification(BaseModel):
    notification_id: str
    event_key: str
    symbol: str
    market: Literal["cn", "hk", "us"]
    timeframe: str
    side: Literal["BUY", "SELL", "RISK"]
    action_name: str
    shape_name: str
    triggered_at: datetime
    trigger_price: float
    snapshot_payload: dict
    read_at: datetime | None = None
```

- [ ] **Step 4: Implement locked, atomic persistence**

Use a single `threading.RLock`; write JSON through `NamedTemporaryFile` in the target directory followed by `Path.replace`. Append notifications only when `event_key` is not already present in the in-memory index. Never mutate an existing JSONL notification.

- [ ] **Step 5: Run store tests**

```powershell
python -m pytest tests/test_dow_monitor_store.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add docs/decisions/2026-07-23-dow-realtime-watch-panel.md docs/superpowers/specs/2026-07-23-dow-realtime-watch-panel-design.md docs/spec-index.yaml backend/app/services/dow_monitor_models.py backend/app/services/dow_monitor_store.py backend/tests/test_dow_monitor_store.py
git commit -m "feat: persist dow monitor state"
```

---

### Task 3: Add a strict WebStock monitor data gateway

**Files:**
- Modify: `backend/app/plugins/clickhouse/provider.py`
- Create: `backend/app/services/dow_monitor_data.py`
- Create: `backend/tests/test_dow_monitor_data.py`
- Modify: `backend/tests/test_clickhouse_provider.py`

**Interfaces:**
- Produces on `ClickHouseProvider`: `get_minute_strict(...) -> pl.DataFrame`, `get_realtime_strict(symbols: list[str]) -> list[dict]`; neither method invokes `_minute_fallback_fn` nor Longbridge HTTP.
- Produces: `WebStockMonitorGateway(provider, now_fn)` with `fetch(symbols, start, end) -> WebStockBatch`.
- `WebStockBatch` contains `quotes`, `minute_rows`, `source_timestamp`, `freshness_by_symbol`, `gap_details`.

- [ ] **Step 1: Write strict-source and stale-data tests**

```python
def test_strict_minute_never_uses_longbridge_fallback():
    fallback = Mock(side_effect=AssertionError("fallback forbidden"))
    provider = ClickHouseProvider(query_fn=lambda sql: [], minute_fallback_fn=fallback)
    assert provider.get_minute_strict(["01347.HK"], start, end).is_empty()
    fallback.assert_not_called()


def test_gateway_marks_stale_quote_and_gap_without_replacement():
    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch(["01347.HK"], start, now)
    assert batch.freshness_by_symbol["01347.HK"].state == "STALE_DATA"
    assert batch.freshness_by_symbol["01347.HK"].reason in {
        "QUOTE_TOO_OLD", "MINUTE_TOO_OLD", "SESSION_GAP"
    }
```

The fixtures must include an HK lunch break so 12:00–13:00 is not reported as a gap.

Run:

```powershell
python -m pytest tests/test_dow_monitor_data.py tests/test_clickhouse_provider.py -q
```

Expected: FAIL because strict provider methods and gateway do not exist.

- [ ] **Step 2: Extract strict ClickHouse queries**

Refactor existing query construction into private `_query_minute_rows(...)` and `_query_realtime_rows(...)`. Keep current `get_minute()` behavior unchanged, while `get_minute_strict()` returns only ClickHouse rows and preserves a `source="webstock"` column.

```python
def get_minute_strict(self, symbols, start_time, end_time, asset_type="stock", freq="1m"):
    rows = self._query_minute_rows(symbols, start_time, end_time, freq)
    return self._normalize_minute_query_rows(rows, symbols, start_time, end_time).with_columns(
        pl.lit("webstock").alias("source")
    )
```

- [ ] **Step 3: Implement market-aware freshness and gap checks**

```python
QUOTE_MAX_AGE = timedelta(seconds=90)
MINUTE_MAX_AGE = timedelta(seconds=120)


def expected_minutes(symbol: str, local_date: date) -> set[datetime]:
    policy = market_session_policy(symbol)
    return {
        cursor.replace(tzinfo=None)
        for start, end in policy.sessions
        for cursor in minute_range(local_date, start, end)
    }
```

Only compare received bars against expected minutes up to `now`. Do not count future minutes, lunch breaks, pre-market or after-hours as missing.

- [ ] **Step 4: Run strict gateway tests**

```powershell
python -m pytest tests/test_dow_monitor_data.py tests/test_clickhouse_provider.py -q
```

Expected: PASS, including characterization tests proving existing provider fallback behavior is unchanged.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/plugins/clickhouse/provider.py backend/app/services/dow_monitor_data.py backend/tests/test_dow_monitor_data.py backend/tests/test_clickhouse_provider.py
git commit -m "feat: add strict webstock monitor gateway"
```

---

### Task 4: Aggregate five market-aware timeframes from one 1-minute sequence

**Files:**
- Create: `backend/app/services/dow_monitor_bars.py`
- Create: `backend/tests/test_dow_monitor_bars.py`

**Interfaces:**
- Produces: `build_timeframes(symbol: str, minute_rows: pl.DataFrame, daily_rows: pl.DataFrame, now: datetime) -> dict[str, TimeframeBars]`.
- `TimeframeBars` contains `completed: list[dict]`, `forming: dict`, `completion: "FORMING" | "FINAL"`, `source_timestamp`.

- [ ] **Step 1: Write failing aggregation tests for all markets**

```python
@pytest.mark.parametrize(
    ("symbol", "zone", "session_bars"),
    [
        ("600519.SH", "Asia/Shanghai", ["09:30", "11:25", "13:00", "14:55"]),
        ("01347.HK", "Asia/Hong_Kong", ["09:30", "11:55", "13:00", "15:55"]),
        ("INTC.US", "America/New_York", ["09:30", "15:55"]),
    ],
)
def test_five_minute_buckets_never_cross_sessions(symbol, zone, session_bars):
    frames = build_timeframes(symbol, minute_fixture(symbol), daily_fixture(symbol), as_of(symbol))
    assert [bar["timestamp"][11:16] for bar in frames["5m"].all_bars] == session_bars
```

Add tests that:
- 15m/30m/60m all derive from the same normalized 1m rows;
- the current bucket is `FORMING`;
- a completed bucket is `FINAL`;
- current daily K merges historical daily rows with today’s minute OHLCV;
- HK/A-share lunch breaks do not create a cross-lunch candle;
- US daylight-saving timezone conversion stays in regular session.

Run:

```powershell
python -m pytest tests/test_dow_monitor_bars.py -q
```

Expected: FAIL because `build_timeframes` does not exist.

- [ ] **Step 2: Implement session-segment anchored bucketing**

```python
TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "30m": 30, "60m": 60}


def bucket_start(local_dt: datetime, session_start: time, minutes: int) -> datetime:
    anchor = datetime.combine(local_dt.date(), session_start, tzinfo=local_dt.tzinfo)
    elapsed = int((local_dt - anchor).total_seconds() // 60)
    return anchor + timedelta(minutes=(elapsed // minutes) * minutes)
```

Aggregate `open=first`, `high=max`, `low=min`, `close=last`, `volume=sum`, `amount=sum`. Start a new bucket at each session segment, so no bar spans an exchange lunch break.

- [ ] **Step 3: Implement forming daily merge**

If today has minute rows, replace or append today’s historical row with the intraday aggregate and set `completion="FORMING"` while the market is open. After regular-session close, mark it `FINAL`.

- [ ] **Step 4: Run aggregation tests**

```powershell
python -m pytest tests/test_dow_monitor_bars.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/services/dow_monitor_bars.py backend/tests/test_dow_monitor_bars.py
git commit -m "feat: aggregate dow monitor timeframes"
```

---

### Task 5: Add the typed Longbridge Dow evaluation client

**Files:**
- Create: `backend/app/services/dow_monitor_client.py`
- Create: `backend/tests/test_dow_monitor_client.py`

**Interfaces:**
- Produces: `LongbridgeDowClient(endpoint: str, timeout_s: float = 20.0)`.
- Produces: `evaluate(symbol, timeframe, bars, completion, as_of) -> DowEngineResult`.
- Must call only `POST {LONGBRIDGE_API_URL}/api/dow-state/evaluate`.

- [ ] **Step 1: Write failing request/response tests**

```python
def test_client_sends_exact_forming_bar_contract(monkeypatch):
    transport = capture_transport(engine_response_fixture())
    result = LongbridgeDowClient("http://127.0.0.1:19912", transport=transport).evaluate(
        "01347.HK", "30m", bars, "FORMING", as_of
    )
    request = transport.requests[0]
    assert request.url.path == "/api/dow-state/evaluate"
    assert request.json()["completion"] == "FORMING"
    assert result.snapshot.line_anchor_times == (
        "2026-07-22T15:00:00+08:00",
        "2026-07-23T10:00:00+08:00",
    )
```

Also assert 502/timeout becomes `DowEngineUnavailable` and never creates a locally inferred signal.

Run:

```powershell
python -m pytest tests/test_dow_monitor_client.py -q
```

Expected: FAIL because the client does not exist.

- [ ] **Step 2: Implement the typed adapter**

```python
class DowEngineUnavailable(RuntimeError):
    pass


class LongbridgeDowClient:
    def evaluate(self, symbol, timeframe, bars, completion, as_of) -> DowEngineResult:
        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "completion": completion,
            "asOf": as_of.isoformat(),
            "bars": bars,
        }
        try:
            response = self._client.post("/api/dow-state/evaluate", json=payload)
            response.raise_for_status()
            return DowEngineResult.model_validate(response.json())
        except (httpx.HTTPError, ValidationError) as exc:
            raise DowEngineUnavailable(str(exc)) from exc
```

- [ ] **Step 3: Run adapter tests**

```powershell
python -m pytest tests/test_dow_monitor_client.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add backend/app/services/dow_monitor_client.py backend/tests/test_dow_monitor_client.py
git commit -m "feat: connect monitor to dow engine"
```

---

### Task 6: Implement background polling, event activation, and recovery

**Files:**
- Create: `backend/app/services/dow_monitor_service.py`
- Create: `backend/tests/test_dow_monitor_service.py`

**Interfaces:**
- Produces: `DowMonitorService(store, data_gateway, dow_client, daily_loader, poll_seconds=15, now_fn=...)`.
- Produces async lifecycle: `start()`, `stop()`, `run_once()`.
- Produces query methods: `overview(market)`, `detail(symbol, timeframe)`, `status()`.

- [ ] **Step 1: Write failing lifecycle and isolation tests**

```python
@pytest.mark.asyncio
async def test_run_once_evaluates_all_five_periods_for_enabled_symbol():
    await service.run_once()
    assert client.calls == [
        ("01347.HK", "5m"), ("01347.HK", "15m"), ("01347.HK", "30m"),
        ("01347.HK", "60m"), ("01347.HK", "day"),
    ]


@pytest.mark.asyncio
async def test_disabled_symbol_is_not_evaluated_but_other_symbols_continue():
    store.upsert_symbol("01347.HK", "hk", enabled=False)
    store.upsert_symbol("INTC.US", "us", enabled=True)
    await service.run_once()
    assert all(symbol == "INTC.US" for symbol, _ in client.calls)
```

Add tests for:
- page-independent background start;
- one symbol failing without stopping others;
- stale WebStock retaining last state and creating no notification;
- Longbridge unavailable producing `ANALYSIS_PAUSED` and no synthetic line;
- recovery replays from last reliable timestamp without duplicate notifications.

Run:

```powershell
python -m pytest tests/test_dow_monitor_service.py -q
```

Expected: FAIL because the service does not exist.

- [ ] **Step 2: Implement one-cycle orchestration**

```python
async def run_once(self) -> None:
    enabled = [item for item in self.store.list_symbols() if item.enabled]
    batch = await asyncio.to_thread(self.data_gateway.fetch, [x.symbol for x in enabled], ...)
    for item in enabled:
        try:
            await self._evaluate_symbol(item, batch)
        except Exception:
            logger.exception("dow monitor symbol failed: %s", item.symbol)
```

`_evaluate_symbol` must save `STALE_DATA` immediately and return before calling the engine when freshness fails.

- [ ] **Step 3: Implement the activation state machine**

```python
def transition_event(previous: ActivationState | None, snapshot: DowSnapshot) -> EventTransition:
    family = signal_family(snapshot.action_code)
    structure_id = snapshot.line_id
    active = family is not None and structure_id is not None
    if not active:
        return EventTransition(next=ActivationState.inactive(previous), notify=False)
    same = previous and previous.active and previous.family == family and previous.structure_id == structure_id
    sequence = previous.activation_sequence if same else (previous.activation_sequence + 1 if previous else 1)
    return EventTransition(
        next=ActivationState(True, family, structure_id, sequence),
        notify=not same,
    )
```

For a notifying transition, copy the entire engine response and current OHLC into `snapshot_payload` before appending. Never keep a reference to mutable current state.

- [ ] **Step 4: Implement the cancellable background loop**

```python
async def _loop(self) -> None:
    while not self._stop.is_set():
        started = monotonic()
        await self.run_once()
        delay = max(0.0, self.poll_seconds - (monotonic() - started))
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=delay)
        except TimeoutError:
            pass
```

`start()` is idempotent; `stop()` sets the event and awaits the task.

- [ ] **Step 5: Run service tests**

```powershell
python -m pytest tests/test_dow_monitor_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add backend/app/services/dow_monitor_service.py backend/tests/test_dow_monitor_service.py
git commit -m "feat: run background dow monitoring"
```

---

### Task 7: Expose monitor APIs and wire the FastAPI lifecycle

**Files:**
- Create: `backend/app/api/dow_monitor.py`
- Create: `backend/tests/test_dow_monitor_api.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- HTTP:
  - `GET/POST /api/dow-monitor/symbols`
  - `DELETE/PATCH /api/dow-monitor/symbols/{symbol}`
  - `GET /api/dow-monitor/overview?market=all|cn|hk|us`
  - `GET /api/dow-monitor/{symbol}?timeframe=5m|15m|30m|60m|day`
  - `GET /api/dow-monitor/notifications?market=all|cn|hk|us&unreadOnly=false`
  - `PATCH /api/dow-monitor/notifications/{notification_id}/read`
  - `GET /api/dow-monitor/status`

- [ ] **Step 1: Write failing API contract tests**

```python
def test_market_filter_changes_response_only_not_enabled_state(client, service):
    response = client.get("/api/dow-monitor/overview?market=hk")
    assert {item["market"] for item in response.json()["symbols"]} == {"hk"}
    assert service.store.get_symbol("INTC.US").enabled is True


def test_patch_switch_persists(client):
    response = client.patch("/api/dow-monitor/symbols/01347.HK", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["enabled"] is False
```

Also cover normalized symbols, unsupported suffix 400, duplicate add idempotence, detail timeframe validation, notification read and status timestamps.

Run:

```powershell
python -m pytest tests/test_dow_monitor_api.py -q
```

Expected: FAIL because router and lifespan wiring do not exist.

- [ ] **Step 2: Implement thin API handlers**

```python
def _service(request: Request) -> DowMonitorService:
    service = getattr(request.app.state, "dow_monitor_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Dow monitor is not initialized")
    return service
```

Handlers validate input and delegate; they do not fetch market data or calculate Dow semantics.

- [ ] **Step 3: Wire lifecycle after custom providers are loaded**

In `lifespan`, resolve the registered `clickhouse` provider, create store/gateway/client/service, assign `app.state.dow_monitor_service`, and `await service.start()`. On shutdown, call `await service.stop()` before closing shared resources.

```python
app.include_router(dow_monitor.router)
```

- [ ] **Step 4: Run API and lifecycle tests**

```powershell
python -m pytest tests/test_dow_monitor_api.py tests/test_dow_monitor_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/api/dow_monitor.py backend/app/main.py backend/tests/test_dow_monitor_api.py
git commit -m "feat: expose dow monitor api"
```

---

### Task 8: Add frontend monitor contracts and query hooks

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/queryKeys.ts`
- Create: `frontend/src/components/dow-monitor/types.ts`
- Create: `frontend/src/components/dow-monitor/useDowMonitor.ts`
- Create: `frontend/src/components/dow-monitor/useDowMonitor.test.tsx`

**Interfaces:**
- Produces TypeScript types matching Task 7.
- Produces hooks: `useDowMonitorOverview(market)`, `useDowNotifications(market)`, `useDowMonitorDetail(symbol, timeframe)`.
- Produces mutations: `addDowMonitorSymbol`, `removeDowMonitorSymbol`, `setDowMonitorEnabled`, `markDowNotificationRead`.

- [ ] **Step 1: Write failing hook tests**

```tsx
it('keeps market filtering as a query parameter and never toggles hidden symbols', async () => {
  renderHook(() => useDowMonitorOverview('hk'), { wrapper })
  expect(await capturedRequest()).toBe('/api/dow-monitor/overview?market=hk')
  expect(fetchMock).not.toHaveBeenCalledWith(
    expect.stringContaining('/symbols/INTC.US'),
    expect.anything(),
  )
})
```

Run:

```powershell
cd E:\my_project\tickflow-stock-panel\frontend
pnpm test --run src/components/dow-monitor/useDowMonitor.test.tsx
```

Expected: FAIL because the hook does not exist.

- [ ] **Step 2: Add exact API methods and query keys**

```typescript
dowMonitorOverview: (market: DowMonitorMarket) => ['dow-monitor', 'overview', market] as const,
dowMonitorNotifications: (market: DowMonitorMarket) => ['dow-monitor', 'notifications', market] as const,
dowMonitorDetail: (symbol: string, timeframe: DowTimeframe) =>
  ['dow-monitor', 'detail', symbol, timeframe] as const,
```

Use a 15-second `refetchInterval` and retain the previous successful payload while a refresh is in flight. Do not derive freshness from browser receipt time; display backend `sourceTimestamp` and `freshnessState`.

- [ ] **Step 3: Run hook tests**

```powershell
pnpm test --run src/components/dow-monitor/useDowMonitor.test.tsx
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add frontend/src/lib/api.ts frontend/src/lib/queryKeys.ts frontend/src/components/dow-monitor/types.ts frontend/src/components/dow-monitor/useDowMonitor.ts frontend/src/components/dow-monitor/useDowMonitor.test.tsx
git commit -m "feat: add dow monitor frontend api"
```

---

### Task 9: Build the compact multi-stock grid, market filters, and signal rail

**Files:**
- Create: `frontend/src/components/dow-monitor/DowMiniChart.tsx`
- Create: `frontend/src/components/dow-monitor/DowMonitorCard.tsx`
- Create: `frontend/src/components/dow-monitor/DowMonitorSignalRail.tsx`
- Create: `frontend/src/pages/DowMonitor.tsx`
- Create: `frontend/src/pages/DowMonitor.test.tsx`

**Interfaces:**
- `DowMiniChart` consumes backend `chart.bars`, `chart.lines`, `chart.signals`.
- `DowMonitorCard` emits `onOpen(symbol, timeframe)` and `onToggle(symbol, enabled)`.
- `DowMonitorSignalRail` consumes already market-filtered notifications.

- [ ] **Step 1: Write failing page behavior tests**

```tsx
it('shows a four-column grid and filters cards plus signals by market', async () => {
  render(<DowMonitor />, { wrapper })
  expect(await screen.findByTestId('dow-monitor-grid')).toHaveClass('2xl:grid-cols-4')
  await userEvent.click(screen.getByRole('button', { name: '港股' }))
  expect(screen.getByText('01347.HK')).toBeInTheDocument()
  expect(screen.queryByText('INTC.US')).not.toBeInTheDocument()
  expect(screen.getByTestId('signal-01347.HK')).toBeInTheDocument()
  expect(screen.queryByTestId('signal-INTC.US')).not.toBeInTheDocument()
})


it('does not pause a symbol when switching market tabs', async () => {
  render(<DowMonitor />, { wrapper })
  await userEvent.click(screen.getByRole('button', { name: '美股' }))
  expect(api.setDowMonitorEnabled).not.toHaveBeenCalled()
})
```

Also test independent switches, five timeframe badges, BUY green/SELL red/WATCH yellow/stale disabled appearance, add/remove symbols, and the “暂无可交易信号” state.

Run:

```powershell
pnpm test --run src/pages/DowMonitor.test.tsx
```

Expected: FAIL because page/components do not exist.

- [ ] **Step 2: Implement the compact grid shell**

```tsx
<div
  data-testid="dow-monitor-grid"
  className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-3"
>
  {filteredSymbols.map(item => <DowMonitorCard key={item.symbol} item={item} />)}
</div>
```

The page filter state is local:

```typescript
type MarketFilter = 'all' | 'cn' | 'hk' | 'us'
type SignalFilter = 'all' | 'active' | 'buy' | 'sell'
```

Filter cards and notifications from the same market value. Never call the enable mutation from a filter handler.

- [ ] **Step 3: Implement the mini chart**

Use the existing ECharts theme colors and candlestick conventions, but omit indicator panels, long prose, axes labels and legends. Draw:
- main lines as solid blue/magenta;
- acceleration lines as dashed variants;
- buy markers green and sell/risk markers red;
- only lines/signals returned by Longbridge.

- [ ] **Step 4: Implement signal rail and card switch**

The fixed rail shows code, timeframe, Chinese action and Chinese shape. The per-stock switch calls only `setDowMonitorEnabled(symbol, enabled)`.

- [ ] **Step 5: Run page tests and build**

```powershell
pnpm test --run src/pages/DowMonitor.test.tsx
pnpm build
```

Expected: tests PASS and TypeScript/Vite build exits 0.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/components/dow-monitor/DowMiniChart.tsx frontend/src/components/dow-monitor/DowMonitorCard.tsx frontend/src/components/dow-monitor/DowMonitorSignalRail.tsx frontend/src/pages/DowMonitor.tsx frontend/src/pages/DowMonitor.test.tsx
git commit -m "feat: build compact dow monitor grid"
```

---

### Task 10: Reuse the full K-line and indicator controls in a detail dialog

**Files:**
- Create: `frontend/src/components/dow-monitor/DowMonitorDetailDialog.tsx`
- Create: `frontend/src/components/dow-monitor/chartMappings.ts`
- Create: `frontend/src/components/dow-monitor/DowMonitorDetailDialog.test.tsx`
- Modify: `frontend/src/pages/DowMonitor.tsx`

**Interfaces:**
- Produces: `toChartMarkers(signals)`, `toPriceLines(lines, bars)`.
- `DowMonitorDetailDialog` consumes `symbol`, `timeframe`, `open`, `onClose`.

- [ ] **Step 1: Write failing dialog tests**

```tsx
it('opens from a card and exposes existing indicator controls', async () => {
  render(<DowMonitor />, { wrapper })
  await userEvent.click(await screen.findByRole('button', { name: /打开 01347.HK 完整K线/ }))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  for (const label of ['成交量', 'MACD', 'RSI', 'KDJ', 'BOLL']) {
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
  }
  expect(screen.getByText(/量比/)).toBeInTheDocument()
  expect(screen.getByText(/均量/)).toBeInTheDocument()
})
```

Also test that closing restores page market filter and scroll position, and that line anchors map to chart dates without locally recomputing anchors.

Run:

```powershell
pnpm test --run src/components/dow-monitor/DowMonitorDetailDialog.test.tsx
```

Expected: FAIL because the dialog/mappers do not exist.

- [ ] **Step 2: Implement engine-to-chart mapping**

```typescript
export function toChartMarkers(signals: DowChartSignal[]): ChartMarker[] {
  return signals.map(signal => ({
    date: signal.time,
    kind: signal.side === 'BUY' ? 'buy' : 'sell',
    above: signal.side !== 'BUY',
    color: signal.side === 'BUY' ? '#10B981' : '#EF4444',
    label: signal.side === 'BUY' ? '买' : '卖',
  }))
}
```

Map each returned line using its two `anchorTimes`/`anchorPrices`; do not choose anchors in TypeScript.

- [ ] **Step 3: Reuse existing chart controls**

For daily K use `StockDailyKChart`; for intraday data use `EChartsCandlestick` with the same `SUB_CHARTS`, `OVERLAY_INDICATORS` and `VolumeCompareConfig` controls. Keep one shared control toolbar component inside the dialog so the semantics remain identical.

- [ ] **Step 4: Run dialog tests and build**

```powershell
pnpm test --run src/components/dow-monitor/DowMonitorDetailDialog.test.tsx
pnpm build
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/components/dow-monitor/DowMonitorDetailDialog.tsx frontend/src/components/dow-monitor/chartMappings.ts frontend/src/components/dow-monitor/DowMonitorDetailDialog.test.tsx frontend/src/pages/DowMonitor.tsx
git commit -m "feat: add dow monitor chart detail"
```

---

### Task 11: Add the page to the existing TickFlow navigation

**Files:**
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/components/MobileNavigation.tsx`
- Create: `frontend/src/pages/dow-monitor-route.test.tsx`

**Interfaces:**
- Route: `/dow-monitor`.
- Navigation label: `趋势监控`.

- [ ] **Step 1: Write the failing route/navigation test**

```tsx
it('exposes trend monitoring in desktop and mobile navigation', () => {
  render(<Layout />, { wrapper })
  expect(screen.getByRole('link', { name: '趋势监控' })).toHaveAttribute('href', '/dow-monitor')
  expect(router.routes).toContainRoute('/dow-monitor')
})
```

Run:

```powershell
pnpm test --run src/pages/dow-monitor-route.test.tsx
```

Expected: FAIL because the route and navigation item do not exist.

- [ ] **Step 2: Add lazy route and existing-framework navigation items**

```tsx
const DowMonitor = lazy(() =>
  import('./pages/DowMonitor').then(module => ({ default: module.DowMonitor }))
)
```

Add `{ path: 'dow-monitor', element: <DowMonitor /> }` and one `RadioTower` navigation item named `趋势监控`. Do not create a second layout, theme or authentication shell.

- [ ] **Step 3: Run route test and complete frontend suite**

```powershell
pnpm test --run
pnpm build
```

Expected: all tests PASS and build exits 0.

- [ ] **Step 4: Commit**

```powershell
git add frontend/src/router.tsx frontend/src/components/Layout.tsx frontend/src/components/MobileNavigation.tsx frontend/src/pages/dow-monitor-route.test.tsx
git commit -m "feat: add trend monitor navigation"
```

---

### Task 12: Perform 01347 semantic acceptance, promote traceability, and add Chronicle health patrol

**Files:**
- Modify: `docs/superpowers/specs/2026-07-23-dow-realtime-watch-panel-design.md`
- Modify: `docs/spec-index.yaml`
- Modify: `docs/traceability.yaml`
- Create: `docs/acceptance/2026-07-23-dow-realtime-watch-panel.md`
- Create: `docs/reviews/2026-07-23-dow-realtime-watch-panel-review.md`
- Create: `scripts/check_dow_monitor_health.py`
- Create: `backend/tests/test_dow_monitor_health_script.py`

**Interfaces:**
- Health probe: `python scripts/check_dow_monitor_health.py --url http://127.0.0.1:3018 --max-age-seconds 120`.
- Chronicle cadence: every 10 minutes; success exit 0, unhealthy/stale service exit 1.

- [ ] **Step 1: Write the failing health-probe test**

```python
def test_health_probe_rejects_stopped_or_stale_monitor(monkeypatch):
    monkeypatch.setattr(
        httpx, "get",
        lambda *args, **kwargs: Response(200, json={
            "running": False,
            "lastSuccessfulCycleAt": "2026-07-23T09:30:00+08:00",
        }),
    )
    assert main(["--url", "http://127.0.0.1:3018", "--max-age-seconds", "120"]) == 1
```

Run:

```powershell
cd E:\my_project\tickflow-stock-panel\backend
python -m pytest tests/test_dow_monitor_health_script.py -q
```

Expected: FAIL because the script does not exist.

- [ ] **Step 2: Implement the health probe**

The script calls `/api/dow-monitor/status`, verifies `running=true`, and verifies `lastSuccessfulCycleAt` is no older than the configured threshold while at least one monitored market is open. Outside all regular sessions, it only requires `running=true`.

- [ ] **Step 3: Run full automated verification**

```powershell
cd E:\my_project\tickflow-stock-panel\backend
python -m pytest tests/test_dow_monitor_store.py tests/test_dow_monitor_data.py tests/test_dow_monitor_bars.py tests/test_dow_monitor_client.py tests/test_dow_monitor_service.py tests/test_dow_monitor_api.py tests/test_dow_monitor_health_script.py -q
cd ..\frontend
pnpm test --run
pnpm build
cd ..
python scripts/check_spec_compliance.py
```

Expected: all tests PASS, frontend build exits 0, specification checker exits 0.

- [ ] **Step 4: Run the 01347.HK semantic acceptance**

1. Add only `01347.HK` and enable it.
2. Verify all five timeframe states originate from the same WebStock 1m batch.
3. For every visible main/acceleration line, compare line ID, role, two anchor times and anchor prices with the Longbridge response.
4. When a forming-bar event appears, record source timestamp, trigger timestamp, timeframe, Chinese shape, Chinese action, line ID, anchors and current OHLC.
5. Keep the event active across two polling cycles and verify only one notification exists.
6. Clear the event, retrigger it, and verify a second notification with incremented activation sequence exists.
7. Simulate stale WebStock and verify the last state remains visible with `数据延迟` and no new notification.
8. Close the page, allow one backend cycle to run, reopen it and verify the persisted notification is present.

Write the observed identifiers and timestamps into `docs/acceptance/2026-07-23-dow-realtime-watch-panel.md`. Do not use “looks similar” or a screenshot as the sole proof.

- [ ] **Step 5: Conduct the independent requirements-to-evidence review**

For each of the ten `REQ-DOW-WATCH-*` IDs, review from the approved specification to:
- exact implementation path;
- exact executable behavioral test;
- exact 01347 semantic evidence where applicable;
- absence of local Dow anchor/signal inference;
- absence of silent realtime fallback;
- absence of systemd changes.

Record findings and command outputs in `docs/reviews/2026-07-23-dow-realtime-watch-panel-review.md`.

- [ ] **Step 6: Promote the approved specification and complete traceability**

Change document status to `已批准并完成 01347.HK 语义验收`, register `SPEC-DOW-WATCH-001` as authoritative with all ten requirement IDs, and map every ID to real implementation, executable test, semantic acceptance and independent review paths.
Remove `EXC-DOW-WATCH-IMPLEMENTATION-001`; the final checker must pass without an exception for this specification.

Run:

```powershell
python scripts/check_spec_compliance.py
```

Expected: PASS with no exception for `SPEC-DOW-WATCH-001`.

- [ ] **Step 7: Register Chronicle patrol**

Using the `chronicle-scheduler` skill, create or update one job named `tickflow-dow-monitor-health`:

```text
schedule: every 10 minutes
command: python E:\my_project\tickflow-stock-panel\scripts\check_dow_monitor_health.py --url http://127.0.0.1:3018 --max-age-seconds 120
working directory: E:\my_project\tickflow-stock-panel
```

Verify the recorded scheduler is Chronicle and confirm there is no new systemd unit.

- [ ] **Step 8: Commit acceptance and compliance evidence**

```powershell
git add docs/superpowers/specs/2026-07-23-dow-realtime-watch-panel-design.md docs/spec-index.yaml docs/traceability.yaml docs/acceptance/2026-07-23-dow-realtime-watch-panel.md docs/reviews/2026-07-23-dow-realtime-watch-panel-review.md scripts/check_dow_monitor_health.py backend/tests/test_dow_monitor_health_script.py
git commit -m "docs: accept realtime dow monitor"
```

Stop after the 01347.HK evidence is delivered for user inspection. Do not add A-share/US acceptance symbols or expand monitoring scale until the user confirms this result.

---

## Requirement Coverage Review

| Requirement | Primary implementation tasks | Executable/semantic gate |
| --- | --- | --- |
| REQ-DOW-WATCH-UI-001 | Tasks 8–9 | `DowMonitor.test.tsx`, 01347 page acceptance |
| REQ-DOW-WATCH-DETAIL-001 | Task 10 | `DowMonitorDetailDialog.test.tsx`, existing control inspection |
| REQ-DOW-WATCH-FILTER-001 | Tasks 8–9 | market/signal filter tests; switch non-mutation test |
| REQ-DOW-WATCH-DATA-001 | Tasks 3–4 | strict WebStock and same-1m-sequence tests |
| REQ-DOW-WATCH-MTF-001 | Tasks 4 and 6 | five-timeframe aggregation/service tests |
| REQ-DOW-WATCH-SIGNAL-001 | Tasks 1, 5 and 6 | lower engine adapter test plus forming-bar service test |
| REQ-DOW-WATCH-NOTIFY-001 | Tasks 2 and 6 | immutable snapshot and activation sequence tests |
| REQ-DOW-WATCH-BACKGROUND-001 | Tasks 6–7 and 12 | lifecycle/page-independent test plus Chronicle patrol |
| REQ-DOW-WATCH-STALE-001 | Tasks 3 and 6 | stale/gap/recovery/no-duplicate tests |
| REQ-DOW-WATCH-MARKET-001 | Task 4 | A/HK/US session aggregation tests; only HK semantic acceptance before user confirmation |

## Final Verification Commands

```powershell
cd E:\my_project\longbridge-stock\.worktrees\universal-intraday-dow-fingerprint
python -m pytest tests/test_dow_external_state.py tests/test_dow_bar_state.py tests/test_dow_multitimeframe_state.py tests/test_dow_multimarket_state.py -q
python scripts/check_spec_compliance.py

cd E:\my_project\tickflow-stock-panel\backend
python -m pytest tests/test_dow_monitor_store.py tests/test_dow_monitor_data.py tests/test_dow_monitor_bars.py tests/test_dow_monitor_client.py tests/test_dow_monitor_service.py tests/test_dow_monitor_api.py tests/test_dow_monitor_health_script.py -q

cd E:\my_project\tickflow-stock-panel\frontend
pnpm test --run
pnpm build

cd E:\my_project\tickflow-stock-panel
python scripts/check_spec_compliance.py
git status --short
```

Expected: both specification checkers exit 0; all selected backend and frontend tests pass; frontend builds; `git status --short` contains no files from the implementation commits.
