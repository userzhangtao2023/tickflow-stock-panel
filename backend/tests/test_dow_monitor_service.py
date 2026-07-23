from __future__ import annotations

import asyncio
import threading
import time
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from app.services.dow_monitor_client import DowEngineResult, DowEngineUnavailable
from app.services.dow_monitor_data import (
    SymbolFreshness,
    WebStockBatch,
    WebStockHistory,
    WebStockHistoryCoverage,
)
from app.services.dow_monitor_models import DowNotification, DowTimeframeState
from app.services.dow_monitor_service import DowMonitorService, transition_event
from app.services.dow_monitor_store import DowMonitorStore

NOW = datetime(2026, 7, 23, 2, 1, tzinfo=UTC)
TIMEFRAMES = ("5m", "15m", "30m", "60m", "day")


def _minute_rows(*symbols: str) -> pl.DataFrame:
    rows = []
    for symbol in symbols:
        local_date = date(2026, 7, 22) if symbol.endswith(".US") else date(2026, 7, 23)
        rows.extend(
            {
                "symbol": symbol,
                "datetime": value,
                "open": price,
                "high": price + 1,
                "low": price - 1,
                "close": price + 0.5,
                "volume": 100.0,
                "amount": 10_000.0,
                "source": "webstock",
            }
            for value, price in (
                (
                    datetime.combine(local_date, datetime.min.time()).replace(hour=9, minute=30),
                    100.0,
                ),
                (
                    datetime.combine(local_date, datetime.min.time()).replace(hour=9, minute=31),
                    101.0,
                ),
                (datetime.combine(local_date, datetime.min.time()).replace(hour=10), 102.0),
            )
        )
    return pl.DataFrame(rows)


def _minute_rows_from_values(symbol: str, values: list[datetime]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": [symbol] * len(values),
            "datetime": [value.replace(tzinfo=None) for value in values],
            "open": [100.0 + index for index in range(len(values))],
            "high": [101.0 + index for index in range(len(values))],
            "low": [99.0 + index for index in range(len(values))],
            "close": [100.5 + index for index in range(len(values))],
            "volume": [100.0] * len(values),
            "amount": [10_000.0] * len(values),
            "source": ["webstock"] * len(values),
        }
    )


def _daily_rows(symbol: str, _: datetime) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": [symbol, symbol],
            "date": [date(2026, 7, 21), date(2026, 7, 22)],
            "open": [95.0, 97.0],
            "high": [99.0, 101.0],
            "low": [94.0, 96.0],
            "close": [98.0, 100.0],
            "volume": [1_000.0, 1_200.0],
            "amount": [98_000.0, 120_000.0],
        }
    )


def _batch(
    *symbols: str,
    freshness: str = "LIVE",
    source_timestamp: datetime = NOW,
) -> WebStockBatch:
    return WebStockBatch(
        quotes=[
            {
                "symbol": symbol,
                "timestamp": int(source_timestamp.timestamp() * 1_000),
                "last_price": 102.5,
            }
            for symbol in symbols
        ],
        minute_rows=_minute_rows(*symbols),
        source_timestamp=source_timestamp,
        freshness_by_symbol={
            symbol: SymbolFreshness(state=freshness, reason=None) for symbol in symbols
        },
        gap_details={symbol: [] for symbol in symbols},
    )


class FakeGateway:
    def __init__(
        self,
        batch: WebStockBatch | Exception,
        history: WebStockHistory | Exception | None = None,
    ) -> None:
        self.batch = batch
        self.history = history
        self.calls: list[tuple[dict[str, datetime], datetime]] = []
        self.history_calls: list[tuple[list[str], datetime]] = []

    def fetch_since(
        self,
        starts_by_symbol: dict[str, datetime],
        end: datetime,
    ) -> WebStockBatch:
        self.calls.append((dict(starts_by_symbol), end))
        if isinstance(self.batch, Exception):
            raise self.batch
        return self.batch

    def load_history(self, symbols: list[str], end: datetime) -> WebStockHistory:
        self.history_calls.append((list(symbols), end))
        if isinstance(self.history, Exception):
            raise self.history
        if self.history is not None:
            return self.history
        return _complete_history(symbols)


def _complete_history(
    symbols: list[str],
    minute_rows: pl.DataFrame | None = None,
) -> WebStockHistory:
    return WebStockHistory(
        minute_rows=minute_rows if minute_rows is not None else pl.DataFrame(),
        coverage_by_symbol={
            symbol: WebStockHistoryCoverage(
                earliest_timestamp=None,
                latest_timestamp=None,
                latest_prior_session_date=date(2026, 7, 22),
                latest_prior_session_complete=True,
                state="COMPLETE",
                reason=None,
            )
            for symbol in symbols
        },
    )


def _engine_result(
    symbol: str,
    timeframe: str,
    bars: list[dict],
    completion: str,
    *,
    action_code: str,
    line_id: str | None,
    evaluated_at: datetime,
    long_operation: str = "观察",
    long_signal_stage: str = "NONE",
    long_line_id: str | None = None,
    long_completion: str | None = None,
    long_provisional: bool | None = None,
) -> DowEngineResult:
    current = bars[-1]
    active = action_code != "WATCH" and line_id is not None
    line = (
        {
            "id": line_id,
            "side": "SUPPORT",
            "role": "MAIN",
            "generation": 0,
            "anchorIndexes": [0, max(0, len(bars) - 2)],
            "anchorTimes": [bars[0]["timestamp"], bars[max(0, len(bars) - 2)]["timestamp"]],
            "anchorPrices": [bars[0]["low"], bars[max(0, len(bars) - 2)]["low"]],
            "createdIndex": max(0, len(bars) - 2),
            "invalidatedIndex": None,
            "controlsSignals": True,
        }
        if active
        else None
    )
    action_names = {
        "WATCH": "观察",
        "OPEN_LONG": "买入\uff08开多\uff09",
        "OPEN_SHORT": "卖出\uff08开空\uff09",
        "CLOSE_LONG": "卖出\uff08平多\uff09",
        "CLOSE_SHORT": "买入\uff08平空\uff09",
    }
    return DowEngineResult.model_validate(
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "snapshot": {
                "symbol": symbol,
                "timeframe": timeframe,
                "bar_time": current["timestamp"],
                "bar_completion": completion,
                "provisional": completion == "FORMING",
                "phase": "首次突破趋势线" if active else "无明确形态",
                "phase_code": "FIRST_BREAK" if active else "NONE",
                "candle_pattern": None,
                "line_id": line_id,
                "line_role": "MAIN" if active else None,
                "line_side": "SUPPORT" if active else None,
                "line_anchor_times": line["anchorTimes"] if line else [],
                "line_value": 99.0 if active else None,
                "price_to_line_pct": 3.0 if active else None,
                "sequence_count": 1 if active else 0,
                "volume_ratio_20": 1.3,
                "volume_confirmation": "CONFIRMED",
                "action": action_names[action_code],
                "action_code": action_code,
                "reason_codes": ["CONTROLLED_BREAK"] if active else [],
            },
            "bars": [
                {
                    "index": index,
                    **{
                        key: bar[key]
                        for key in (
                            "timestamp",
                            "open",
                            "high",
                            "low",
                            "close",
                            "volume",
                        )
                    },
                }
                for index, bar in enumerate(bars)
            ],
            "lines": [line] if line else [],
            "signals": [],
            "longTerm": {
                "symbol": symbol,
                "timeframe": timeframe,
                "bar_time": current["timestamp"],
                "bar_completion": long_completion or completion,
                "provisional": (
                    long_provisional
                    if long_provisional is not None
                    else (long_completion or completion) == "FORMING"
                ),
                "trend_direction": "DOWN",
                "trend_name": "长期下降趋势",
                "pattern_name": "长期下降趋势双突破",
                "operation": long_operation,
                "signal_stage": long_signal_stage,
                "breakout_type": "DOUBLE_BREAKOUT",
                "line_id": long_line_id,
                "line_side": "RESISTANCE" if long_line_id else None,
                "line_status": "BROKEN" if long_line_id else None,
                "first_anchor_time": bars[0]["timestamp"] if long_line_id else None,
                "first_anchor_price": bars[0]["high"] if long_line_id else None,
                "second_anchor_time": (
                    bars[max(0, len(bars) - 2)]["timestamp"] if long_line_id else None
                ),
                "second_anchor_price": (
                    bars[max(0, len(bars) - 2)]["high"] if long_line_id else None
                ),
                "line_value": 101.0 if long_line_id else None,
                "key_level_type": "PRIMARY_LL" if long_line_id else None,
                "key_level_time": bars[0]["timestamp"] if long_line_id else None,
                "key_level_price": bars[0]["low"] if long_line_id else None,
                "first_break_time": current["timestamp"] if long_line_id else None,
                "recent_low_scale": "PRIMARY",
                "recent_low_label": "LL",
                "recent_low_time": bars[0]["timestamp"],
                "recent_low_price": bars[0]["low"],
                "recent_low_confirmed_time": bars[0]["timestamp"],
                "evidence_codes": ["LONG_LINE_BREAK", "KEY_LEVEL_BREAK"],
                "failure_reason": None,
            },
            "evaluatedAt": evaluated_at.isoformat(),
        }
    )


class FakeClient:
    def __init__(
        self,
        *,
        action_code: str = "WATCH",
        line_id: str | None = None,
        fail_symbols: set[str] | None = None,
        fail_timeframes: set[str] | None = None,
        unexpected_timeframes: set[str] | None = None,
        long_operation: str = "观察",
        long_signal_stage: str = "NONE",
        long_line_id: str | None = None,
        long_completion: str | None = None,
        long_provisional: bool | None = None,
    ) -> None:
        self.action_code = action_code
        self.line_id = line_id
        self.fail_symbols = fail_symbols or set()
        self.fail_timeframes = fail_timeframes or set()
        self.unexpected_timeframes = unexpected_timeframes or set()
        self.long_operation = long_operation
        self.long_signal_stage = long_signal_stage
        self.long_line_id = long_line_id
        self.long_completion = long_completion
        self.long_provisional = long_provisional
        self.calls: list[tuple[str, str]] = []
        self.received: list[tuple[str, str, list[dict]]] = []
        self.completions: list[tuple[str, str, str]] = []
        self.called = threading.Event()
        self.last_result: DowEngineResult | None = None

    def evaluate(
        self,
        symbol: str,
        timeframe: str,
        bars: list[dict],
        completion: str,
        as_of: datetime,
    ) -> DowEngineResult:
        self.calls.append((symbol, timeframe))
        self.received.append((symbol, timeframe, deepcopy(bars)))
        self.completions.append((symbol, timeframe, completion))
        self.called.set()
        if symbol in self.fail_symbols:
            raise DowEngineUnavailable(f"{symbol} unavailable")
        if timeframe in self.fail_timeframes:
            raise DowEngineUnavailable(f"{symbol} {timeframe} unavailable")
        if timeframe in self.unexpected_timeframes:
            raise RuntimeError(f"{symbol} {timeframe} unexpected")
        self.last_result = _engine_result(
            symbol,
            timeframe,
            bars,
            completion,
            action_code=self.action_code,
            line_id=self.line_id,
            evaluated_at=as_of,
            long_operation=self.long_operation,
            long_signal_stage=self.long_signal_stage,
            long_line_id=self.long_line_id,
            long_completion=self.long_completion,
            long_provisional=self.long_provisional,
        )
        return self.last_result


def _service(
    tmp_path,
    *,
    symbols: tuple[tuple[str, str, bool], ...] = (("01347.HK", "hk", True),),
    batch: WebStockBatch | Exception | None = None,
    client: FakeClient | None = None,
    poll_seconds: float = 15,
):
    store = DowMonitorStore(tmp_path)
    for symbol, market, enabled in symbols:
        store.upsert_symbol(symbol, market, enabled)
    gateway = FakeGateway(batch or _batch(*(item[0] for item in symbols)))
    client = client or FakeClient()
    service = DowMonitorService(
        store,
        gateway,
        client,
        _daily_rows,
        poll_seconds=poll_seconds,
        now_fn=lambda: NOW,
    )
    return service, store, gateway, client


def _seed_reliable_states(
    store: DowMonitorStore,
    symbol: str,
    market: str,
    source_timestamp: datetime,
) -> None:
    for timeframe in TIMEFRAMES:
        store.save_state(
            DowTimeframeState(
                symbol=symbol,
                market=market,
                timeframe=timeframe,
                freshness_state="LIVE",
                source_timestamp=source_timestamp,
                snapshot={"action_code": "WATCH", "line_id": None},
                chart={"bars": [], "lines": [], "signals": []},
                updated_at=source_timestamp,
            )
        )


@pytest.mark.parametrize("line_id", ["", "   "])
def test_local_transition_preserves_non_none_structure_identity_baseline(
    line_id: str,
) -> None:
    snapshot = _engine_result(
        "01347.HK",
        "30m",
        [
            {
                "timestamp": NOW.isoformat(),
                "open": 100.0,
                "high": 103.0,
                "low": 99.0,
                "close": 102.0,
                "volume": 100.0,
            }
        ],
        "FINAL",
        action_code="OPEN_LONG",
        line_id=line_id,
        evaluated_at=NOW,
    ).snapshot

    transition = transition_event(None, snapshot)

    assert transition.notify is True
    assert transition.next.active is True
    assert transition.next.family == "OPEN_LONG"
    assert transition.next.structure_id == line_id
    assert transition.next.activation_sequence == 1


@pytest.mark.asyncio
async def test_run_once_evaluates_all_five_periods_only_for_enabled_symbols(tmp_path) -> None:
    service, _, gateway, client = _service(
        tmp_path,
        symbols=(("01347.HK", "hk", False), ("INTC.US", "us", True)),
        batch=_batch("INTC.US"),
    )

    await service.run_once()

    assert len(gateway.calls) == 1
    assert client.calls == [("INTC.US", timeframe) for timeframe in TIMEFRAMES]


@pytest.mark.asyncio
async def test_background_start_is_page_independent_idempotent_and_stop_awaits_task(
    tmp_path,
) -> None:
    service, _, _, client = _service(tmp_path, poll_seconds=3_600)

    await service.start()
    first_task = service._task
    await service.start()
    await asyncio.to_thread(client.called.wait, 1)

    assert service._task is first_task
    assert service.status()["running"] is True
    await service.stop()
    assert first_task is not None and first_task.done()
    assert service.status()["running"] is False


@pytest.mark.asyncio
async def test_one_symbol_engine_failure_does_not_stop_other_symbol(tmp_path) -> None:
    client = FakeClient(fail_symbols={"01347.HK"})
    service, store, _, _ = _service(
        tmp_path,
        symbols=(("01347.HK", "hk", True), ("INTC.US", "us", True)),
        batch=_batch("01347.HK", "INTC.US"),
        client=client,
    )

    await service.run_once()

    assert client.calls == [
        *(("01347.HK", timeframe) for timeframe in TIMEFRAMES),
        *(("INTC.US", timeframe) for timeframe in TIMEFRAMES),
    ]
    assert store.get_state("01347.HK", "30m").freshness_state == "ANALYSIS_PAUSED"
    assert store.get_state("INTC.US", "30m").freshness_state == "LIVE"
    assert "01347.HK unavailable" in service.status()["errors"]["01347.HK"]


@pytest.mark.asyncio
async def test_stale_webstock_retains_snapshot_and_chart_and_sends_no_notification(
    tmp_path,
) -> None:
    service, store, _, client = _service(
        tmp_path,
        batch=_batch("01347.HK", freshness="STALE_DATA"),
        client=FakeClient(action_code="OPEN_LONG", line_id="LINE-1"),
    )
    old_snapshot = {"action_code": "OPEN_LONG", "line_id": "LINE-OLD"}
    old_chart = {"bars": [{"close": 88.0}], "lines": [{"id": "LINE-OLD"}]}
    store.save_state(
        DowTimeframeState(
            symbol="01347.HK",
            market="hk",
            timeframe="30m",
            freshness_state="LIVE",
            source_timestamp=NOW - timedelta(minutes=5),
            snapshot=deepcopy(old_snapshot),
            chart=deepcopy(old_chart),
            updated_at=NOW - timedelta(minutes=5),
        )
    )

    await service.run_once()

    state = store.get_state("01347.HK", "30m")
    assert state.freshness_state == "STALE_DATA"
    assert state.snapshot == old_snapshot
    assert state.chart == old_chart
    assert state.source_timestamp == NOW - timedelta(minutes=5)
    assert client.calls == []
    assert store.list_notifications() == []


@pytest.mark.asyncio
async def test_webstock_failure_marks_all_existing_states_stale_without_engine_call(
    tmp_path,
) -> None:
    service, store, _, client = _service(tmp_path, batch=RuntimeError("webstock down"))
    store.save_state(
        DowTimeframeState(
            symbol="01347.HK",
            market="hk",
            timeframe="5m",
            freshness_state="LIVE",
            source_timestamp=NOW - timedelta(minutes=2),
            snapshot={"action_code": "WATCH"},
            chart={"bars": [{"close": 100.0}]},
            updated_at=NOW - timedelta(minutes=2),
        )
    )

    await service.run_once()

    assert store.get_state("01347.HK", "5m").freshness_state == "STALE_DATA"
    assert client.calls == []
    assert service.status()["last_error"] == "webstock down"


@pytest.mark.asyncio
async def test_longbridge_unavailable_retains_state_and_never_synthesizes_line(
    tmp_path,
) -> None:
    client = FakeClient(fail_symbols={"01347.HK"})
    service, store, _, _ = _service(tmp_path, client=client)
    old_snapshot = {"action_code": "WATCH", "line_id": None}
    old_chart = {"bars": [{"close": 90.0}], "lines": []}
    store.save_state(
        DowTimeframeState(
            symbol="01347.HK",
            market="hk",
            timeframe="30m",
            freshness_state="LIVE",
            source_timestamp=NOW - timedelta(minutes=1),
            snapshot=deepcopy(old_snapshot),
            chart=deepcopy(old_chart),
            updated_at=NOW - timedelta(minutes=1),
        )
    )

    await service.run_once()

    state = store.get_state("01347.HK", "30m")
    assert state.freshness_state == "ANALYSIS_PAUSED"
    assert state.snapshot == old_snapshot
    assert state.chart == old_chart
    assert state.chart["lines"] == []
    assert store.list_notifications() == []


@pytest.mark.asyncio
async def test_activation_notifies_once_then_reactivation_uses_next_sequence_and_deepcopy(
    tmp_path,
) -> None:
    client = FakeClient(action_code="OPEN_LONG", line_id="LINE-1")
    current_now = NOW
    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    gateway = FakeGateway(_batch("01347.HK"))
    service = DowMonitorService(
        store,
        gateway,
        client,
        _daily_rows,
        now_fn=lambda: current_now,
    )

    await service.run_once()
    first = next(item for item in store.list_notifications() if item.timeframe == "30m")
    assert first.event_key == "01347.HK|30m|OPEN_LONG|LINE-1|1"
    assert first.side == "BUY"
    assert first.action_name == "买入\uff08开多\uff09"
    assert first.shape_name == "首次突破趋势线"
    assert first.snapshot_payload["engine"]["snapshot"]["action_code"] == "OPEN_LONG"
    assert first.snapshot_payload["current_ohlc"]["close"] == 102.5
    frozen = deepcopy(first.snapshot_payload)
    client.last_result.snapshot.action_code = "WATCH"
    persisted = next(item for item in store.list_notifications() if item.timeframe == "30m")
    assert persisted.snapshot_payload == frozen

    client.action_code = "OPEN_LONG"
    current_now += timedelta(minutes=1)
    await service.run_once()
    assert len([item for item in store.list_notifications() if item.timeframe == "30m"]) == 1

    client.action_code = "WATCH"
    client.line_id = None
    current_now += timedelta(minutes=1)
    await service.run_once()
    assert len([item for item in store.list_notifications() if item.timeframe == "30m"]) == 1
    watch_state = store.get_state("01347.HK", "30m")
    store.save_state(watch_state.model_copy(update={"source_timestamp": current_now}))

    store = DowMonitorStore(tmp_path)
    service = DowMonitorService(
        store,
        gateway,
        client,
        _daily_rows,
        now_fn=lambda: NOW,
    )
    client.action_code = "OPEN_LONG"
    client.line_id = "LINE-1"
    current_now += timedelta(minutes=1)
    await service.run_once()
    keys = {item.event_key for item in store.list_notifications() if item.timeframe == "30m"}
    assert keys == {
        "01347.HK|30m|OPEN_LONG|LINE-1|1",
        "01347.HK|30m|OPEN_LONG|LINE-1|2",
    }


@pytest.mark.asyncio
async def test_watch_is_not_a_trade_notification_and_close_is_risk_family(tmp_path) -> None:
    client = FakeClient(action_code="WATCH", line_id="LINE-1")
    service, store, _, _ = _service(tmp_path, client=client)
    await service.run_once()
    assert store.list_notifications() == []

    client.action_code = "CLOSE_LONG"
    await service.run_once()
    assert {item.side for item in store.list_notifications()} == {"RISK"}


@pytest.mark.asyncio
async def test_local_and_long_term_events_coexist_and_full_sidecar_is_persisted(
    tmp_path,
) -> None:
    client = FakeClient(
        action_code="OPEN_LONG",
        line_id="LINE-1",
        long_operation="买入触发",
        long_signal_stage="TRIGGER",
        long_line_id="LONG-RESISTANCE-7",
        long_completion="FINAL",
    )
    service, store, _, _ = _service(tmp_path, client=client)

    await service.run_once()

    notices = [item for item in store.list_notifications() if item.timeframe == "30m"]
    assert {item.event_key for item in notices} == {
        "01347.HK|30m|OPEN_LONG|LINE-1|1",
        "01347.HK|30m|LONG_TERM_BUY|LONG-RESISTANCE-7|1",
    }
    state = store.get_state("01347.HK", "30m")
    assert state.snapshot["action_code"] == "OPEN_LONG"
    assert state.chart["lines"][0]["id"] == "LINE-1"
    assert state.chart["longTerm"]["line_id"] == "LONG-RESISTANCE-7"
    assert state.chart["longTerm"]["first_anchor_time"] is not None
    assert state.chart["longTerm"]["pattern_name"] == "长期下降趋势双突破"
    assert state.chart["longTerm"]["operation"] == "买入触发"
    assert state.chart["longTerm"]["signal_stage"] == "TRIGGER"
    assert state.chart["longTerm"]["evidence_codes"] == [
        "LONG_LINE_BREAK",
        "KEY_LEVEL_BREAK",
    ]


@pytest.mark.asyncio
async def test_forming_long_term_trigger_is_display_only(tmp_path) -> None:
    client = FakeClient(
        long_operation="买入触发",
        long_signal_stage="TRIGGER",
        long_line_id="LONG-RESISTANCE-7",
        long_completion="FORMING",
    )
    service, store, _, _ = _service(tmp_path, client=client)

    await service.run_once()

    assert store.list_notifications() == []
    state = store.get_state("01347.HK", "30m")
    assert state.chart["longTerm"]["operation"] == "买入触发"
    assert state.chart["longTerm"]["bar_completion"] == "FORMING"


@pytest.mark.parametrize(
    ("provisional", "line_id"),
    [
        (True, "LONG-RESISTANCE-7"),
        (False, None),
        (False, ""),
        (False, "   "),
    ],
)
@pytest.mark.asyncio
async def test_invalid_formal_long_term_identity_is_display_only(
    tmp_path,
    provisional: bool,
    line_id: str | None,
) -> None:
    client = FakeClient(
        long_operation="买入触发",
        long_signal_stage="TRIGGER",
        long_line_id=line_id,
        long_completion="FINAL",
        long_provisional=provisional,
    )
    service, store, _, _ = _service(tmp_path, client=client)

    await service.run_once()

    assert store.list_notifications() == []
    sidecar = store.get_state("01347.HK", "30m").chart["longTerm"]
    assert sidecar["provisional"] is provisional
    assert sidecar["line_id"] == line_id


@pytest.mark.asyncio
async def test_long_term_event_dedupes_then_reactivation_uses_its_own_sequence(
    tmp_path,
) -> None:
    client = FakeClient(
        long_operation="卖出触发",
        long_signal_stage="CONFIRMED",
        long_line_id="LONG-SUPPORT-9",
        long_completion="FINAL",
    )
    current_now = NOW
    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    service = DowMonitorService(
        store,
        FakeGateway(_batch("01347.HK")),
        client,
        _daily_rows,
        now_fn=lambda: current_now,
    )

    await service.run_once()
    current_now += timedelta(minutes=1)
    await service.run_once()
    client.long_operation = "观察"
    client.long_signal_stage = "NONE"
    client.long_line_id = None
    current_now += timedelta(minutes=1)
    await service.run_once()
    inactive = store.get_state("01347.HK", "30m")
    store.save_state(inactive.model_copy(update={"source_timestamp": current_now}))
    client.long_operation = "卖出触发"
    client.long_signal_stage = "CONFIRMED"
    client.long_line_id = "LONG-SUPPORT-9"
    current_now += timedelta(minutes=1)
    await service.run_once()

    keys = {item.event_key for item in store.list_notifications() if item.timeframe == "30m"}
    assert keys == {
        "01347.HK|30m|LONG_TERM_SELL|LONG-SUPPORT-9|1",
        "01347.HK|30m|LONG_TERM_SELL|LONG-SUPPORT-9|2",
    }


@pytest.mark.asyncio
async def test_long_term_first_state_crash_recovers_from_notification_history(
    tmp_path,
) -> None:
    class SimulatedProcessCrash(BaseException):
        pass

    class CrashAfterLongNotificationStore(DowMonitorStore):
        crashed = False

        def save_state(self, state):
            long_written = any(
                "|LONG_TERM_BUY|" in item.event_key for item in self.list_notifications(limit=100)
            )
            if state.timeframe == "30m" and long_written and not self.crashed:
                self.crashed = True
                raise SimulatedProcessCrash
            return super().save_state(state)

    client = FakeClient(
        long_operation="买入触发",
        long_signal_stage="TRIGGER",
        long_line_id="LONG-RESISTANCE-7",
        long_completion="FINAL",
    )
    store = CrashAfterLongNotificationStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    service = DowMonitorService(
        store,
        FakeGateway(_batch("01347.HK")),
        client,
        _daily_rows,
        now_fn=lambda: NOW,
    )

    with pytest.raises(SimulatedProcessCrash):
        await service.run_once()
    restored = DowMonitorStore(tmp_path)
    restarted = DowMonitorService(
        restored,
        FakeGateway(_batch("01347.HK")),
        client,
        _daily_rows,
        now_fn=lambda: NOW + timedelta(minutes=1),
    )
    await restarted.run_once()

    keys = [item.event_key for item in restored.list_notifications() if item.timeframe == "30m"]
    assert keys == ["01347.HK|30m|LONG_TERM_BUY|LONG-RESISTANCE-7|1"]


@pytest.mark.asyncio
async def test_long_term_existing_state_crash_recovers_from_notification_history(
    tmp_path,
) -> None:
    class SimulatedProcessCrash(BaseException):
        pass

    class CrashAfterLongNotificationStore(DowMonitorStore):
        crash_enabled = False
        crashed = False

        def save_state(self, state):
            long_written = any(
                "|LONG_TERM_BUY|" in item.event_key for item in self.list_notifications(limit=100)
            )
            if (
                self.crash_enabled
                and state.timeframe == "30m"
                and long_written
                and not self.crashed
            ):
                self.crashed = True
                raise SimulatedProcessCrash
            return super().save_state(state)

    client = FakeClient()
    store = CrashAfterLongNotificationStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    service = DowMonitorService(
        store,
        FakeGateway(_batch("01347.HK")),
        client,
        _daily_rows,
        now_fn=lambda: NOW,
    )
    await service.run_once()
    assert store.get_state("01347.HK", "30m") is not None

    client.long_operation = "买入触发"
    client.long_signal_stage = "TRIGGER"
    client.long_line_id = "  LONG-RESISTANCE-7  "
    client.long_completion = "FINAL"
    store.crash_enabled = True
    with pytest.raises(SimulatedProcessCrash):
        await service.run_once()

    restored = DowMonitorStore(tmp_path)
    restarted = DowMonitorService(
        restored,
        FakeGateway(_batch("01347.HK", source_timestamp=NOW + timedelta(minutes=1))),
        client,
        _daily_rows,
        now_fn=lambda: NOW + timedelta(minutes=1),
    )
    await restarted.run_once()

    keys = [item.event_key for item in restored.list_notifications() if item.timeframe == "30m"]
    assert keys == ["01347.HK|30m|LONG_TERM_BUY|LONG-RESISTANCE-7|1"]


@pytest.mark.asyncio
async def test_restart_recovers_from_last_reliable_timestamp_without_duplicate_event(
    tmp_path,
) -> None:
    reliable_at = NOW - timedelta(minutes=30)
    client = FakeClient(action_code="OPEN_LONG", line_id="LINE-1")
    service, store, gateway, _ = _service(tmp_path, client=client)
    snapshot = _engine_result(
        "01347.HK",
        "30m",
        [
            {
                "timestamp": reliable_at.isoformat(),
                "open": 99.0,
                "high": 103.0,
                "low": 98.0,
                "close": 102.0,
                "volume": 100.0,
            }
        ],
        "FORMING",
        action_code="OPEN_LONG",
        line_id="LINE-1",
        evaluated_at=reliable_at,
    ).snapshot.model_dump(mode="json")
    store.save_state(
        DowTimeframeState(
            symbol="01347.HK",
            market="hk",
            timeframe="30m",
            freshness_state="STALE_DATA",
            source_timestamp=reliable_at,
            snapshot=snapshot,
            chart={
                "bars": [
                    {
                        "timestamp": reliable_at.isoformat(),
                        "open": 99.0,
                        "high": 103.0,
                        "low": 98.0,
                        "close": 102.0,
                        "volume": 100.0,
                    }
                ],
                "lines": [{"id": "LINE-1"}],
            },
            updated_at=reliable_at,
        )
    )
    for timeframe in set(TIMEFRAMES) - {"30m"}:
        store.save_state(
            DowTimeframeState(
                symbol="01347.HK",
                market="hk",
                timeframe=timeframe,
                freshness_state="STALE_DATA",
                source_timestamp=reliable_at,
                snapshot={"action_code": "WATCH", "line_id": None},
                chart={"bars": [], "lines": [], "signals": []},
                updated_at=reliable_at,
            )
        )
    store.append_notification(
        DowNotification(
            notification_id="existing",
            event_key="01347.HK|30m|OPEN_LONG|LINE-1|1",
            symbol="01347.HK",
            market="hk",
            timeframe="30m",
            side="BUY",
            action_name="买入\uff08开多\uff09",
            shape_name="首次突破趋势线",
            triggered_at=reliable_at,
            trigger_price=102.0,
            snapshot_payload={"engine": {"snapshot": snapshot}},
        )
    )
    store = DowMonitorStore(tmp_path)
    service = DowMonitorService(
        store,
        gateway,
        client,
        _daily_rows,
        now_fn=lambda: NOW,
    )

    await service.run_once()

    assert gateway.calls[0][0]["01347.HK"] == reliable_at
    assert gateway.calls[0][1] == NOW
    notices = [item for item in store.list_notifications() if item.timeframe == "30m"]
    assert [item.event_key for item in notices] == ["01347.HK|30m|OPEN_LONG|LINE-1|1"]
    assert store.get_state("01347.HK", "30m").freshness_state == "LIVE"


@pytest.mark.asyncio
async def test_restart_after_notification_write_does_not_emit_next_sequence(tmp_path) -> None:
    inactive_at = NOW - timedelta(minutes=2)
    notification_at = NOW - timedelta(minutes=1)
    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    for timeframe in TIMEFRAMES:
        store.save_state(
            DowTimeframeState(
                symbol="01347.HK",
                market="hk",
                timeframe=timeframe,
                freshness_state="LIVE",
                source_timestamp=inactive_at,
                snapshot={
                    "action_code": "WATCH",
                    "line_id": None,
                    "bar_completion": "FORMING",
                },
                chart={"bars": [], "lines": [], "signals": []},
                updated_at=inactive_at,
            )
        )
    store.append_notification(
        DowNotification(
            notification_id="written-before-crash",
            event_key="01347.HK|30m|OPEN_LONG|LINE-1|1",
            symbol="01347.HK",
            market="hk",
            timeframe="30m",
            side="BUY",
            action_name="买入\uff08开多\uff09",
            shape_name="首次突破趋势线",
            triggered_at=notification_at,
            trigger_price=102.0,
            snapshot_payload={
                "engine": {
                    "snapshot": {
                        "action_code": "OPEN_LONG",
                        "line_id": "LINE-1",
                    }
                },
                "activation": {
                    "active": True,
                    "family": "OPEN_LONG",
                    "structure_id": "LINE-1",
                    "activation_sequence": 1,
                },
                "source_timestamp": notification_at.isoformat(),
            },
        )
    )
    restored = DowMonitorStore(tmp_path)
    service = DowMonitorService(
        restored,
        FakeGateway(_batch("01347.HK")),
        FakeClient(action_code="OPEN_LONG", line_id="LINE-1"),
        _daily_rows,
        now_fn=lambda: NOW,
    )

    await service.run_once()

    keys = [item.event_key for item in restored.list_notifications() if item.timeframe == "30m"]
    assert keys == ["01347.HK|30m|OPEN_LONG|LINE-1|1"]


@pytest.mark.asyncio
async def test_restart_after_first_notification_write_before_any_state_does_not_emit_sequence_two(
    tmp_path,
) -> None:
    class SimulatedProcessCrash(BaseException):
        pass

    class CrashAfterFirstNotificationStore(DowMonitorStore):
        crashed = False

        def save_state(self, state):
            notification_written = any(
                item.timeframe == "30m" for item in self.list_notifications(limit=100)
            )
            if state.timeframe == "30m" and notification_written and not self.crashed:
                self.crashed = True
                raise SimulatedProcessCrash
            return super().save_state(state)

    crashing_store = CrashAfterFirstNotificationStore(tmp_path)
    crashing_store.upsert_symbol("01347.HK", "hk", True)
    client = FakeClient(action_code="OPEN_LONG", line_id="LINE-1")
    crashing_service = DowMonitorService(
        crashing_store,
        FakeGateway(_batch("01347.HK")),
        client,
        _daily_rows,
        now_fn=lambda: NOW,
    )

    with pytest.raises(SimulatedProcessCrash):
        await crashing_service.run_once()

    persisted_after_crash = DowMonitorStore(tmp_path)
    assert persisted_after_crash.get_state("01347.HK", "30m") is None
    first_keys = [
        item.event_key
        for item in persisted_after_crash.list_notifications()
        if item.timeframe == "30m"
    ]
    assert first_keys == ["01347.HK|30m|OPEN_LONG|LINE-1|1"]

    restarted = DowMonitorService(
        persisted_after_crash,
        FakeGateway(_batch("01347.HK")),
        FakeClient(action_code="OPEN_LONG", line_id="LINE-1"),
        _daily_rows,
        now_fn=lambda: NOW + timedelta(minutes=1),
    )
    await restarted.run_once()

    keys_after_restart = [
        item.event_key
        for item in persisted_after_crash.list_notifications()
        if item.timeframe == "30m"
    ]
    assert keys_after_restart == ["01347.HK|30m|OPEN_LONG|LINE-1|1"]


@pytest.mark.asyncio
async def test_new_symbol_forces_full_history_cold_start_in_shared_batch(tmp_path) -> None:
    service, store, gateway, _ = _service(
        tmp_path,
        symbols=(("01347.HK", "hk", True), ("INTC.US", "us", True)),
        batch=_batch("01347.HK", "INTC.US"),
    )
    store.save_state(
        DowTimeframeState(
            symbol="01347.HK",
            market="hk",
            timeframe="30m",
            freshness_state="LIVE",
            source_timestamp=NOW - timedelta(minutes=1),
            snapshot={"action_code": "WATCH", "line_id": None},
            chart={"bars": []},
            updated_at=NOW - timedelta(minutes=1),
        )
    )

    await service.run_once()

    hk_midnight = datetime(2026, 7, 23, tzinfo=ZoneInfo("Asia/Hong_Kong"))
    assert gateway.calls[0][0]["01347.HK"] == hk_midnight.astimezone(UTC)
    us_midnight = datetime(2026, 7, 22, tzinfo=ZoneInfo("America/New_York"))
    assert gateway.calls[0][0]["INTC.US"] == us_midnight.astimezone(UTC)


@pytest.mark.asyncio
async def test_incremental_recovery_merges_prior_context_without_duplicate_minutes(
    tmp_path,
) -> None:
    hk = ZoneInfo("Asia/Hong_Kong")
    first_now = datetime(2026, 7, 23, 10, 3, tzinfo=hk)
    second_now = datetime(2026, 7, 23, 10, 5, tzinfo=hk)
    current_now = first_now
    all_minutes = [
        datetime(2026, 7, 23, 9, 30, tzinfo=hk) + timedelta(minutes=offset) for offset in range(36)
    ]

    class RangeAwareGateway:
        def __init__(self) -> None:
            self.calls = []

        def fetch_since(self, starts_by_symbol, end):
            self.calls.append((dict(starts_by_symbol), end))
            start = starts_by_symbol["01347.HK"]
            visible = [value for value in all_minutes if start <= value <= end]
            return WebStockBatch(
                quotes=[],
                minute_rows=_minute_rows_from_values("01347.HK", visible),
                source_timestamp=max(visible),
                freshness_by_symbol={"01347.HK": SymbolFreshness(state="LIVE", reason=None)},
                gap_details={"01347.HK": []},
            )

        def load_history(self, symbols, end):
            return _complete_history(symbols)

    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    gateway = RangeAwareGateway()
    client = FakeClient()
    service = DowMonitorService(
        store,
        gateway,
        client,
        _daily_rows,
        now_fn=lambda: current_now,
    )

    await service.run_once()
    current_now = second_now
    await service.run_once()

    assert gateway.calls[1][0]["01347.HK"] == first_now
    second_5m = next(bars for _, timeframe, bars in client.received[5:] if timeframe == "5m")
    timestamps = [bar["timestamp"] for bar in second_5m]
    assert timestamps[0].endswith("09:30:00+08:00")
    assert timestamps[-1].endswith("10:05:00+08:00")
    assert len(timestamps) == len(set(timestamps))
    second_60m = next(bars for _, timeframe, bars in client.received[5:] if timeframe == "60m")
    assert second_60m[-1]["volume"] == 3_600.0


@pytest.mark.asyncio
async def test_timeframe_recovery_uses_its_own_cutoff_without_replaying_healthy_volume(
    tmp_path,
) -> None:
    hk = ZoneInfo("Asia/Hong_Kong")
    current_now = datetime(2026, 7, 23, 10, 3, tzinfo=hk)
    all_minutes = [
        datetime(2026, 7, 23, 9, 30, tzinfo=hk) + timedelta(minutes=offset) for offset in range(38)
    ]

    class RangeAwareGateway:
        def fetch_since(self, starts_by_symbol, end):
            start = starts_by_symbol["01347.HK"]
            visible = [value for value in all_minutes if start <= value <= end]
            return WebStockBatch(
                quotes=[],
                minute_rows=_minute_rows_from_values("01347.HK", visible),
                source_timestamp=max(visible),
                freshness_by_symbol={"01347.HK": SymbolFreshness(state="LIVE", reason=None)},
                gap_details={"01347.HK": []},
            )

        def load_history(self, symbols, end):
            return _complete_history(symbols)

    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    client = FakeClient()
    service = DowMonitorService(
        store,
        RangeAwareGateway(),
        client,
        _daily_rows,
        now_fn=lambda: current_now,
    )

    await service.run_once()
    current_now = datetime(2026, 7, 23, 10, 5, tzinfo=hk)
    client.fail_timeframes = {"15m"}
    await service.run_once()
    current_now = datetime(2026, 7, 23, 10, 7, tzinfo=hk)
    client.fail_timeframes.clear()
    await service.run_once()

    third_calls = client.received[10:]
    third_5m = next(bars for _, timeframe, bars in third_calls if timeframe == "5m")
    third_15m = next(bars for _, timeframe, bars in third_calls if timeframe == "15m")
    assert third_5m[-1]["timestamp"].endswith("10:05:00+08:00")
    assert third_5m[-1]["volume"] == 300.0
    assert third_15m[-1]["timestamp"].endswith("10:00:00+08:00")
    assert third_15m[-1]["volume"] == 800.0


@pytest.mark.asyncio
async def test_empty_close_poll_finalizes_prior_forming_buckets_without_recounting_volume(
    tmp_path,
) -> None:
    hk = ZoneInfo("Asia/Hong_Kong")
    before_close = datetime(2026, 7, 23, 15, 59, tzinfo=hk)
    at_close = datetime(2026, 7, 23, 16, 0, tzinfo=hk)
    current_now = before_close
    all_minutes = [
        datetime(2026, 7, 23, 15, 0, tzinfo=hk) + timedelta(minutes=offset) for offset in range(60)
    ]

    class CloseGateway:
        def fetch_since(self, starts_by_symbol, end):
            start = starts_by_symbol["01347.HK"]
            visible = [value for value in all_minutes if start <= value <= end]
            return WebStockBatch(
                quotes=[],
                minute_rows=_minute_rows_from_values("01347.HK", visible),
                source_timestamp=max(visible),
                freshness_by_symbol={"01347.HK": SymbolFreshness(state="LIVE", reason=None)},
                gap_details={"01347.HK": []},
            )

        def load_history(self, symbols, end):
            return _complete_history(symbols)

    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    client = FakeClient()
    service = DowMonitorService(
        store,
        CloseGateway(),
        client,
        _daily_rows,
        now_fn=lambda: current_now,
    )

    await service.run_once()
    first_5m_volume = next(
        bars[-1]["volume"] for _, timeframe, bars in client.received if timeframe == "5m"
    )
    current_now = at_close
    await service.run_once()

    second_completions = dict(
        (timeframe, completion) for _, timeframe, completion in client.completions[5:]
    )
    assert second_completions["5m"] == "FINAL"
    assert second_completions["60m"] == "FINAL"
    second_5m_volume = next(
        bars[-1]["volume"] for _, timeframe, bars in client.received[5:] if timeframe == "5m"
    )
    assert second_5m_volume == first_5m_volume


@pytest.mark.asyncio
async def test_daily_loader_failure_pauses_old_live_state_and_is_visible(tmp_path) -> None:
    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    store.save_state(
        DowTimeframeState(
            symbol="01347.HK",
            market="hk",
            timeframe="30m",
            freshness_state="LIVE",
            source_timestamp=NOW - timedelta(minutes=1),
            snapshot={"action_code": "WATCH", "line_id": None},
            chart={"bars": [{"close": 100.0}], "lines": []},
            updated_at=NOW - timedelta(minutes=1),
        )
    )

    def broken_daily_loader(_: str, __: datetime) -> pl.DataFrame:
        raise RuntimeError("daily history unavailable")

    service = DowMonitorService(
        store,
        FakeGateway(_batch("01347.HK")),
        FakeClient(),
        broken_daily_loader,
        now_fn=lambda: NOW,
    )

    await service.run_once()

    state = store.get_state("01347.HK", "30m")
    assert state.freshness_state == "ANALYSIS_PAUSED"
    assert state.chart["bars"] == [{"close": 100.0}]
    assert service.status()["errors"]["01347.HK"] == "daily history unavailable"


@pytest.mark.asyncio
async def test_queries_expose_source_freshness_success_error_and_running(tmp_path) -> None:
    service, _, _, _ = _service(tmp_path)

    await service.run_once()

    overview = service.overview("hk")
    detail = service.detail("01347.HK", "30m")
    status = service.status()
    assert overview["symbols"][0]["states"]["30m"]["source_timestamp"] is not None
    assert overview["symbols"][0]["states"]["30m"]["freshness_state"] == "LIVE"
    assert detail["source_timestamp"] is not None
    assert detail["freshness_state"] == "LIVE"
    assert status["last_success_at"] is not None
    assert status["last_error"] is None
    assert status["running"] is False


@pytest.mark.asyncio
async def test_cold_start_keeps_t_minus_one_across_a_share_long_holiday(tmp_path) -> None:
    shanghai = ZoneInfo("Asia/Shanghai")
    current_now = datetime(2026, 10, 9, 10, 0, tzinfo=shanghai)
    history_minutes = [
        *(
            datetime(2026, 9, 30, 9, 30, tzinfo=shanghai) + timedelta(minutes=offset)
            for offset in range(120)
        ),
        *(
            datetime(2026, 9, 30, 13, 0, tzinfo=shanghai) + timedelta(minutes=offset)
            for offset in range(120)
        ),
    ]
    live_minutes = [datetime(2026, 10, 9, 9, 30, tzinfo=shanghai)]

    class HolidayGateway:
        def __init__(self) -> None:
            self.calls = []
            self.history_calls = []

        def fetch_since(self, starts_by_symbol, end):
            self.calls.append((dict(starts_by_symbol), end))
            return WebStockBatch(
                quotes=[],
                minute_rows=_minute_rows_from_values("600519.SH", live_minutes),
                source_timestamp=max(live_minutes),
                freshness_by_symbol={"600519.SH": SymbolFreshness(state="LIVE", reason=None)},
                gap_details={"600519.SH": []},
            )

        def load_history(self, symbols, end):
            self.history_calls.append((list(symbols), end))
            return _complete_history(
                symbols,
                _minute_rows_from_values("600519.SH", history_minutes),
            )

    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("600519.SH", "cn", True)
    gateway = HolidayGateway()
    client = FakeClient()
    service = DowMonitorService(
        store,
        gateway,
        client,
        _daily_rows,
        now_fn=lambda: current_now,
    )

    await service.run_once()

    midnight = datetime(2026, 10, 9, tzinfo=shanghai).astimezone(UTC)
    assert gateway.calls[0][0]["600519.SH"] == midnight
    assert gateway.history_calls == [(["600519.SH"], current_now)]
    bars = next(bars for _, timeframe, bars in client.received if timeframe == "5m")
    assert bars[0]["timestamp"].startswith("2026-09-30")
    assert bars[-1]["timestamp"].startswith("2026-10-09")


@pytest.mark.asyncio
async def test_cold_start_preserves_intc_131_bar_30m_context(tmp_path) -> None:
    new_york = ZoneInfo("America/New_York")
    current_now = datetime(2026, 7, 22, 16, 1, tzinfo=new_york)
    trading_dates = [
        date(2026, 7, 8),
        date(2026, 7, 9),
        date(2026, 7, 10),
        date(2026, 7, 13),
        date(2026, 7, 14),
        date(2026, 7, 15),
        date(2026, 7, 16),
        date(2026, 7, 17),
        date(2026, 7, 20),
        date(2026, 7, 21),
        date(2026, 7, 22),
    ]
    candidates = [
        datetime.combine(day, datetime.min.time(), tzinfo=new_york).replace(hour=9, minute=30)
        + timedelta(minutes=30 * bucket)
        for day in trading_dates
        for bucket in range(13)
    ]
    minutes = [*candidates[:130], candidates[-1]]

    class IntcHistoryGateway:
        def __init__(self) -> None:
            self.calls = []
            self.history_calls = []

        def fetch_since(self, starts_by_symbol, end):
            self.calls.append((dict(starts_by_symbol), end))
            return WebStockBatch(
                quotes=[],
                minute_rows=pl.DataFrame(),
                source_timestamp=current_now,
                freshness_by_symbol={"INTC.US": SymbolFreshness(state="LIVE", reason=None)},
                gap_details={"INTC.US": []},
            )

        def load_history(self, symbols, end):
            self.history_calls.append((list(symbols), end))
            return _complete_history(
                symbols,
                _minute_rows_from_values("INTC.US", minutes),
            )

    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("INTC.US", "us", True)
    gateway = IntcHistoryGateway()
    client = FakeClient()
    service = DowMonitorService(
        store,
        gateway,
        client,
        _daily_rows,
        now_fn=lambda: current_now,
    )

    await service.run_once()

    bars = next(bars for _, timeframe, bars in client.received if timeframe == "30m")
    midnight = datetime(2026, 7, 22, tzinfo=new_york).astimezone(UTC)
    assert gateway.calls[0][0]["INTC.US"] == midnight
    assert gateway.history_calls == [(["INTC.US"], current_now)]
    assert len(bars) == 131
    assert bars[0]["timestamp"].startswith("2026-07-08")
    assert bars[-1]["timestamp"].startswith("2026-07-22")


@pytest.mark.asyncio
async def test_complete_latest_t_minus_one_allows_arbitrary_older_history_gaps(
    tmp_path,
) -> None:
    hk = ZoneInfo("Asia/Hong_Kong")
    history_rows = _minute_rows_from_values(
        "01347.HK",
        [
            datetime(2026, 6, 1, 9, 30, tzinfo=hk),
            datetime(2026, 7, 22, 9, 30, tzinfo=hk),
            datetime(2026, 7, 22, 15, 59, tzinfo=hk),
        ],
    )
    gateway = FakeGateway(
        _batch("01347.HK"),
        _complete_history(["01347.HK"], history_rows),
    )
    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    client = FakeClient()
    service = DowMonitorService(
        store,
        gateway,
        client,
        _daily_rows,
        now_fn=lambda: NOW,
    )

    await service.run_once()

    assert len(client.calls) == 5
    assert store.get_state("01347.HK", "30m").freshness_state == "LIVE"
    assert service.status()["errors"] == {}


@pytest.mark.asyncio
async def test_incomplete_latest_t_minus_one_pauses_cold_symbol_without_engine(
    tmp_path,
) -> None:
    coverage = WebStockHistoryCoverage(
        earliest_timestamp=NOW - timedelta(days=10),
        latest_timestamp=NOW - timedelta(days=1),
        latest_prior_session_date=date(2026, 7, 22),
        latest_prior_session_complete=False,
        state="INCOMPLETE",
        reason="LATEST_PRIOR_SESSION_INCOMPLETE",
    )
    history = WebStockHistory(
        minute_rows=_minute_rows("01347.HK"),
        coverage_by_symbol={"01347.HK": coverage},
    )
    service, store, _, client = _service(
        tmp_path,
        batch=_batch("01347.HK"),
    )
    service._data_gateway.history = history

    await service.run_once()

    assert client.calls == []
    assert {store.get_state("01347.HK", timeframe).freshness_state for timeframe in TIMEFRAMES} == {
        "ANALYSIS_PAUSED"
    }
    assert (
        service.status()["errors"]["01347.HK"]
        == "HISTORY_INCOMPLETE:LATEST_PRIOR_SESSION_INCOMPLETE"
    )


@pytest.mark.asyncio
async def test_cold_symbol_does_not_lower_hot_symbol_live_fetch_start(tmp_path) -> None:
    hot_at = NOW - timedelta(minutes=30)
    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    store.upsert_symbol("INTC.US", "us", True)
    _seed_reliable_states(store, "01347.HK", "hk", hot_at)
    gateway = FakeGateway(_batch("01347.HK", "INTC.US"))
    client = FakeClient()
    service = DowMonitorService(
        store,
        gateway,
        client,
        _daily_rows,
        now_fn=lambda: NOW,
    )

    await service.run_once()

    starts = gateway.calls[0][0]
    assert starts["01347.HK"] == hot_at
    us_midnight = datetime(2026, 7, 22, tzinfo=ZoneInfo("America/New_York"))
    assert starts["INTC.US"] == us_midnight.astimezone(UTC)
    assert gateway.history_calls == [(["INTC.US"], NOW)]
    assert store.get_state("01347.HK", "5m").freshness_state == "LIVE"
    assert store.get_state("INTC.US", "5m").freshness_state == "LIVE"


@pytest.mark.asyncio
async def test_history_live_overlap_is_deduplicated_before_aggregation(tmp_path) -> None:
    hk = ZoneInfo("Asia/Hong_Kong")
    overlap = datetime(2026, 7, 23, 9, 30, tzinfo=hk)
    overlap_rows = _minute_rows_from_values("01347.HK", [overlap])
    batch = WebStockBatch(
        quotes=[],
        minute_rows=overlap_rows,
        source_timestamp=overlap,
        freshness_by_symbol={"01347.HK": SymbolFreshness(state="LIVE", reason=None)},
        gap_details={"01347.HK": []},
    )
    gateway = FakeGateway(
        batch,
        _complete_history(["01347.HK"], overlap_rows),
    )
    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    client = FakeClient()
    service = DowMonitorService(
        store,
        gateway,
        client,
        _daily_rows,
        now_fn=lambda: NOW,
    )

    await service.run_once()

    bars = next(bars for _, timeframe, bars in client.received if timeframe == "5m")
    assert bars[-1]["volume"] == 100.0


@pytest.mark.asyncio
async def test_successful_cold_warmup_is_not_loaded_again_next_cycle(tmp_path) -> None:
    service, _, gateway, _ = _service(tmp_path)

    await service.run_once()
    await service.run_once()

    assert gateway.history_calls == [(["01347.HK"], NOW)]
    assert len(gateway.calls) == 2


@pytest.mark.asyncio
async def test_history_load_failure_pauses_cold_but_hot_symbol_continues(tmp_path) -> None:
    hot_at = NOW - timedelta(minutes=30)
    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    store.upsert_symbol("INTC.US", "us", True)
    _seed_reliable_states(store, "01347.HK", "hk", hot_at)
    gateway = FakeGateway(
        _batch("01347.HK", "INTC.US"),
        RuntimeError("history provider down"),
    )
    client = FakeClient()
    service = DowMonitorService(
        store,
        gateway,
        client,
        _daily_rows,
        now_fn=lambda: NOW,
    )

    await service.run_once()

    assert client.calls == [("01347.HK", timeframe) for timeframe in TIMEFRAMES]
    assert store.get_state("01347.HK", "30m").freshness_state == "LIVE"
    assert store.get_state("INTC.US", "30m").freshness_state == "ANALYSIS_PAUSED"
    assert service.status()["errors"]["INTC.US"] == "history provider down"


@pytest.mark.asyncio
async def test_stale_mark_after_notification_crash_does_not_create_sequence_two(
    tmp_path,
) -> None:
    inactive_at = NOW - timedelta(minutes=3)
    notification_at = NOW - timedelta(minutes=2)
    store = DowMonitorStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    for timeframe in TIMEFRAMES:
        store.save_state(
            DowTimeframeState(
                symbol="01347.HK",
                market="hk",
                timeframe=timeframe,
                freshness_state="LIVE",
                source_timestamp=inactive_at,
                snapshot={"action_code": "WATCH", "line_id": None},
                chart={"bars": [], "lines": [], "signals": []},
                updated_at=inactive_at,
            )
        )
    store.append_notification(
        DowNotification(
            notification_id="written-before-stale",
            event_key="01347.HK|30m|OPEN_LONG|LINE-1|1",
            symbol="01347.HK",
            market="hk",
            timeframe="30m",
            side="BUY",
            action_name="买入",
            shape_name="首次突破趋势线",
            triggered_at=notification_at,
            trigger_price=102.0,
            snapshot_payload={
                "engine": {"snapshot": {"action_code": "OPEN_LONG", "line_id": "LINE-1"}},
                "activation": {
                    "active": True,
                    "family": "OPEN_LONG",
                    "structure_id": "LINE-1",
                    "activation_sequence": 1,
                },
                "source_timestamp": notification_at.isoformat(),
            },
        )
    )
    stale_service = DowMonitorService(
        store,
        FakeGateway(RuntimeError("webstock down")),
        FakeClient(),
        _daily_rows,
        now_fn=lambda: NOW - timedelta(minutes=1),
    )
    await stale_service.run_once()
    assert store.get_state("01347.HK", "30m").updated_at == NOW - timedelta(minutes=1)

    restored = DowMonitorStore(tmp_path)
    service = DowMonitorService(
        restored,
        FakeGateway(_batch("01347.HK")),
        FakeClient(action_code="OPEN_LONG", line_id="LINE-1"),
        _daily_rows,
        now_fn=lambda: NOW,
    )
    await service.run_once()

    keys = [item.event_key for item in restored.list_notifications() if item.timeframe == "30m"]
    assert keys == ["01347.HK|30m|OPEN_LONG|LINE-1|1"]


@pytest.mark.asyncio
async def test_unexpected_timeframe_error_pauses_only_that_frame_and_continues(
    tmp_path,
) -> None:
    client = FakeClient(unexpected_timeframes={"15m"})
    service, store, _, _ = _service(tmp_path, client=client)

    await service.run_once()

    assert client.calls == [("01347.HK", timeframe) for timeframe in TIMEFRAMES]
    assert store.get_state("01347.HK", "5m").freshness_state == "LIVE"
    assert store.get_state("01347.HK", "15m").freshness_state == "ANALYSIS_PAUSED"
    assert store.get_state("01347.HK", "30m").freshness_state == "LIVE"
    assert store.get_state("01347.HK", "60m").freshness_state == "LIVE"
    assert store.get_state("01347.HK", "day").freshness_state == "LIVE"
    assert "15m unexpected" in service.status()["errors"]["01347.HK"]


@pytest.mark.asyncio
async def test_last_success_is_isolated_per_symbol_and_recovers_from_store(tmp_path) -> None:
    client = FakeClient(fail_symbols={"01347.HK"})
    service, store, _, _ = _service(
        tmp_path,
        symbols=(("01347.HK", "hk", True), ("INTC.US", "us", True)),
        batch=_batch("01347.HK", "INTC.US"),
        client=client,
    )

    await service.run_once()

    by_symbol = {item["symbol"]: item for item in service.overview()["symbols"]}
    assert by_symbol["01347.HK"]["last_success_at"] is None
    assert by_symbol["INTC.US"]["last_success_at"] == NOW.isoformat()
    persisted_success = max(
        store.get_state("INTC.US", timeframe).source_timestamp for timeframe in TIMEFRAMES
    )

    restarted = DowMonitorService(
        DowMonitorStore(tmp_path),
        FakeGateway(_batch("01347.HK", "INTC.US")),
        FakeClient(),
        _daily_rows,
        now_fn=lambda: NOW + timedelta(minutes=1),
    )
    restarted_by_symbol = {item["symbol"]: item for item in restarted.overview()["symbols"]}
    assert restarted_by_symbol["01347.HK"]["last_success_at"] is None
    assert restarted_by_symbol["INTC.US"]["last_success_at"] == persisted_success.isoformat()


@pytest.mark.asyncio
async def test_background_cycle_keeps_event_loop_responsive_during_store_io(tmp_path) -> None:
    class SlowStore(DowMonitorStore):
        def list_symbols(self):
            time.sleep(0.15)
            return super().list_symbols()

    store = SlowStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    service = DowMonitorService(
        store,
        FakeGateway(_batch("01347.HK")),
        FakeClient(),
        _daily_rows,
        now_fn=lambda: NOW,
    )

    started = time.perf_counter()
    cycle = asyncio.create_task(service.run_once())
    await asyncio.sleep(0.02)
    elapsed = time.perf_counter() - started
    await cycle

    assert elapsed < 0.1


@pytest.mark.asyncio
async def test_cycle_builds_one_notification_index_instead_of_scanning_per_frame(
    tmp_path,
) -> None:
    class CountingStore(DowMonitorStore):
        notification_scans = 0

        def list_notifications(self, *args, **kwargs):
            self.notification_scans += 1
            return super().list_notifications(*args, **kwargs)

    store = CountingStore(tmp_path)
    store.upsert_symbol("01347.HK", "hk", True)
    service = DowMonitorService(
        store,
        FakeGateway(_batch("01347.HK")),
        FakeClient(),
        _daily_rows,
        now_fn=lambda: NOW,
    )

    await service.run_once()

    assert store.notification_scans == 1
