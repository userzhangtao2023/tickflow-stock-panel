from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import polars as pl

from app.services.dow_monitor_data import (
    WebStockMonitorGateway,
    expected_minutes,
)


HK = ZoneInfo("Asia/Hong_Kong")
SYMBOL = "01347.HK"


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


def _rows_through(last_minute: datetime) -> list[dict]:
    session_date = last_minute.date()
    return [
        {"symbol": SYMBOL, "datetime": minute}
        for minute in sorted(expected_minutes(SYMBOL, session_date))
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
