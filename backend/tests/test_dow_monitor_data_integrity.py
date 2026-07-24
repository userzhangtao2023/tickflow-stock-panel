from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import polars as pl

from app.services.dow_monitor_data import (
    WebStockMonitorGateway,
    expected_minutes,
)
from app.services.dow_monitor_models import MonitoredSymbol
from app.services.dow_monitor_service import DowMonitorService


HK = ZoneInfo("Asia/Hong_Kong")
SYMBOL = "01347.HK"
US_SYMBOL = "AAPL.US"


class _Provider:
    def __init__(self, rows: list[dict], quote_time: datetime) -> None:
        self._rows = rows
        self._quote_time = quote_time

    def get_realtime_strict(self, symbols: list[str]) -> list[dict]:
        return [{"symbol": symbol, "timestamp": self._quote_time} for symbol in symbols]

    def get_minute_strict(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime,
    ) -> pl.DataFrame:
        return pl.DataFrame(self._rows)


def _rows_through(last_minute: datetime, symbol: str = SYMBOL) -> list[dict]:
    session_date = last_minute.date()
    return [
        {"symbol": symbol, "datetime": minute}
        for minute in sorted(expected_minutes(symbol, session_date))
        if minute <= last_minute.replace(tzinfo=None)
    ]


def test_closed_session_missing_tail_is_reported_as_session_gap() -> None:
    now = datetime(2026, 7, 24, 18, 0, tzinfo=HK)
    provider = _Provider(
        _rows_through(datetime(2026, 7, 24, 13, 15, tzinfo=HK)),
        now.astimezone(UTC),
    )
    batch = WebStockMonitorGateway(
        provider,
        now_fn=lambda: now,
    ).fetch(
        [SYMBOL],
        datetime(2026, 7, 24, 9, 30, tzinfo=HK),
        now,
    )

    assert batch.freshness_by_symbol[SYMBOL].state == "STALE_DATA"
    assert batch.freshness_by_symbol[SYMBOL].reason == "SESSION_GAP"
    assert batch.gap_details[SYMBOL][0] == datetime(2026, 7, 24, 13, 16)
    assert batch.gap_details[SYMBOL][-1] == datetime(2026, 7, 24, 15, 59)


def test_closed_complete_session_remains_live() -> None:
    now = datetime(2026, 7, 24, 18, 0, tzinfo=HK)
    provider = _Provider(
        _rows_through(datetime(2026, 7, 24, 15, 59, tzinfo=HK)),
        now.astimezone(UTC),
    )
    batch = WebStockMonitorGateway(
        provider,
        now_fn=lambda: now,
    ).fetch(
        [SYMBOL],
        datetime(2026, 7, 24, 9, 30, tzinfo=HK),
        now,
    )

    assert batch.freshness_by_symbol[SYMBOL].state == "LIVE"
    assert batch.gap_details[SYMBOL] == []


def test_closed_session_with_zero_rows_is_not_live() -> None:
    now = datetime(2026, 7, 24, 18, 0, tzinfo=HK)
    batch = WebStockMonitorGateway(
        _Provider([], now.astimezone(UTC)),
        now_fn=lambda: now,
    ).fetch(
        [SYMBOL],
        datetime(2026, 7, 24, 9, 30, tzinfo=HK),
        now,
    )

    assert batch.freshness_by_symbol[SYMBOL].state == "STALE_DATA"
    assert batch.freshness_by_symbol[SYMBOL].reason == "SESSION_GAP"
    assert batch.gap_details[SYMBOL][0] == datetime(2026, 7, 24, 9, 30)
    assert batch.gap_details[SYMBOL][-1] == datetime(2026, 7, 24, 15, 59)


def test_weekend_check_detects_a_completely_missing_friday_session() -> None:
    now = datetime(2026, 7, 25, 12, 0, tzinfo=HK)
    rows = _rows_through(datetime(2026, 7, 23, 15, 59, tzinfo=HK))
    batch = WebStockMonitorGateway(
        _Provider(rows, now.astimezone(UTC)),
        now_fn=lambda: now,
    ).fetch(
        [SYMBOL],
        datetime(2026, 7, 23, 9, 30, tzinfo=HK),
        now,
    )

    assert batch.freshness_by_symbol[SYMBOL].reason == "SESSION_GAP"
    friday_gaps = [
        minute
        for minute in batch.gap_details[SYMBOL]
        if minute.date().isoformat() == "2026-07-24"
    ]
    assert friday_gaps[0] == datetime(2026, 7, 24, 9, 30)
    assert friday_gaps[-1] == datetime(2026, 7, 24, 15, 59)


def test_weekend_cold_start_queries_and_validates_the_latest_completed_session() -> None:
    now = datetime(2026, 7, 25, 12, 0, tzinfo=HK)

    class ColdStore:
        @staticmethod
        def get_state(symbol: str, timeframe: str):
            return None

    service = DowMonitorService(ColdStore(), None, None, lambda *_args: pl.DataFrame())
    monitored = MonitoredSymbol(
        symbol=SYMBOL,
        market="hk",
        enabled=True,
        created_at=now.astimezone(UTC),
        updated_at=now.astimezone(UTC),
    )
    starts, cold_symbols = service._fetch_plan([monitored], now.astimezone(UTC))

    assert cold_symbols == {SYMBOL}
    assert starts[SYMBOL].astimezone(HK) == datetime(2026, 7, 24, 9, 30, tzinfo=HK)

    batch = WebStockMonitorGateway(
        _Provider([], now.astimezone(UTC)),
        now_fn=lambda: now,
    ).fetch_since(starts, now)
    assert batch.freshness_by_symbol[SYMBOL].reason == "SESSION_GAP"
    assert batch.gap_details[SYMBOL][0] == datetime(2026, 7, 24, 9, 30)
    assert batch.gap_details[SYMBOL][-1] == datetime(2026, 7, 24, 15, 59)


def test_history_coverage_does_not_accept_thursday_when_friday_is_missing() -> None:
    now = datetime(2026, 7, 25, 12, 0, tzinfo=HK)
    history = WebStockMonitorGateway(
        _Provider(
            _rows_through(datetime(2026, 7, 23, 15, 59, tzinfo=HK)),
            now.astimezone(UTC),
        ),
        now_fn=lambda: now,
    ).load_history([SYMBOL], now)

    coverage = history.coverage_by_symbol[SYMBOL]
    assert coverage.latest_prior_session_date.isoformat() == "2026-07-24"
    assert coverage.state == "INCOMPLETE"
    assert coverage.reason == "LATEST_PRIOR_SESSION_INCOMPLETE"


def test_lunch_break_with_zero_morning_rows_is_not_live() -> None:
    now = datetime(2026, 7, 24, 12, 30, tzinfo=HK)
    batch = WebStockMonitorGateway(
        _Provider([], now.astimezone(UTC)),
        now_fn=lambda: now,
    ).fetch(
        [SYMBOL],
        datetime(2026, 7, 24, 9, 30, tzinfo=HK),
        now,
    )

    assert batch.freshness_by_symbol[SYMBOL].reason == "SESSION_GAP"
    assert batch.gap_details[SYMBOL][0] == datetime(2026, 7, 24, 9, 30)
    assert batch.gap_details[SYMBOL][-1] == datetime(2026, 7, 24, 11, 59)


def test_lunch_break_reports_missing_morning_minutes() -> None:
    now = datetime(2026, 7, 24, 12, 30, tzinfo=HK)
    batch = WebStockMonitorGateway(
        _Provider(
            [{"symbol": SYMBOL, "datetime": datetime(2026, 7, 24, 9, 30, tzinfo=HK)}],
            now.astimezone(UTC),
        ),
        now_fn=lambda: now,
    ).fetch(
        [SYMBOL],
        datetime(2026, 7, 24, 9, 30, tzinfo=HK),
        now,
    )

    assert batch.freshness_by_symbol[SYMBOL].reason == "SESSION_GAP"
    assert batch.gap_details[SYMBOL][0] == datetime(2026, 7, 24, 9, 31)
    assert batch.gap_details[SYMBOL][-1] == datetime(2026, 7, 24, 11, 59)


def test_us_early_close_uses_the_actual_exchange_session() -> None:
    ny = ZoneInfo("America/New_York")
    now = datetime(2026, 11, 27, 14, 0, tzinfo=ny)
    open_minute = datetime(2026, 11, 27, 9, 30, tzinfo=ny)
    rows = [
        {"symbol": US_SYMBOL, "datetime": open_minute + timedelta(minutes=offset)}
        for offset in range(210)
    ]
    batch = WebStockMonitorGateway(
        _Provider(rows, now.astimezone(UTC)),
        now_fn=lambda: now,
    ).fetch(
        [US_SYMBOL],
        datetime(2026, 11, 27, 9, 30, tzinfo=ny),
        now,
    )

    assert batch.freshness_by_symbol[US_SYMBOL].state == "LIVE"
    assert batch.gap_details[US_SYMBOL] == []
