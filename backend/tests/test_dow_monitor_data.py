from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import polars as pl

from app.services.dow_monitor_data import (
    WebStockMonitorGateway,
    expected_minutes,
    market_session_policy,
)

HK = ZoneInfo("Asia/Hong_Kong")
US = ZoneInfo("America/New_York")


class StubStrictProvider:
    def __init__(self, *, quotes: list[dict], minute_rows: pl.DataFrame) -> None:
        self.quotes = quotes
        self.minute_rows = minute_rows
        self.calls: list[tuple] = []

    def get_realtime_strict(self, symbols: list[str]) -> list[dict]:
        self.calls.append(("realtime", symbols))
        return self.quotes

    def get_minute_strict(
        self,
        symbols: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> pl.DataFrame:
        self.calls.append(("minute", symbols, start_time, end_time))
        return self.minute_rows


def _quote(symbol: str, at: datetime) -> dict:
    return {
        "symbol": symbol,
        "market": "hk",
        "last_price": 140.5,
        "prev_close": 139,
        "open": 140,
        "high": 141,
        "low": 139,
        "volume": 100,
        "amount": 14050,
        "change_amount": 1.5,
        "change_pct": 0.010791,
        "timestamp": int(at.timestamp() * 1000),
    }


def _minutes(symbol: str, *values: datetime) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": [symbol] * len(values),
            "datetime": [value.replace(tzinfo=None) for value in values],
            "open": [140.0] * len(values),
            "high": [141.0] * len(values),
            "low": [139.0] * len(values),
            "close": [140.5] * len(values),
            "volume": [100.0] * len(values),
            "amount": [14050.0] * len(values),
            "source": ["webstock"] * len(values),
        }
    )


def test_gateway_marks_stale_quote_without_replacement() -> None:
    now = datetime(2026, 7, 23, 10, 5, tzinfo=HK)
    quote_time = now - timedelta(seconds=91)
    rows = _minutes(
        "01347.HK",
        *(datetime(2026, 7, 23, 10, minute, tzinfo=HK) for minute in range(6)),
    )
    provider = StubStrictProvider(quotes=[_quote("01347.HK", quote_time)], minute_rows=rows)

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch(
        ["01347.HK"],
        datetime(2026, 7, 23, 10, 0, tzinfo=HK),
        now,
    )

    assert batch.freshness_by_symbol["01347.HK"].state == "STALE_DATA"
    assert batch.freshness_by_symbol["01347.HK"].reason == "QUOTE_TOO_OLD"
    assert batch.quotes[0]["timestamp"] == int(quote_time.timestamp() * 1000)
    assert batch.minute_rows.get_column("source").unique().to_list() == ["webstock"]
    assert batch.source_timestamp == now.astimezone(UTC)
    assert provider.calls == [
        ("realtime", ["01347.HK"]),
        (
            "minute",
            ["01347.HK"],
            datetime(2026, 7, 23, 10, 0, tzinfo=HK),
            now,
        ),
    ]


def test_gateway_enforces_120_second_minute_freshness() -> None:
    now = datetime(2026, 7, 23, 10, 5, tzinfo=HK)
    provider = StubStrictProvider(
        quotes=[_quote("01347.HK", now)],
        minute_rows=_minutes("01347.HK", now - timedelta(seconds=121)),
    )

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch(
        ["01347.HK"],
        now - timedelta(minutes=3),
        now,
    )

    assert batch.freshness_by_symbol["01347.HK"].state == "STALE_DATA"
    assert batch.freshness_by_symbol["01347.HK"].reason == "MINUTE_TOO_OLD"


def test_gateway_accepts_quote_at_90_second_freshness_limit() -> None:
    now = datetime(2026, 7, 23, 10, 5, tzinfo=HK)
    provider = StubStrictProvider(
        quotes=[_quote("01347.HK", now - timedelta(seconds=90))],
        minute_rows=_minutes("01347.HK", now),
    )

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch(
        ["01347.HK"],
        now,
        now,
    )

    assert batch.freshness_by_symbol["01347.HK"].state == "LIVE"


def test_gateway_accepts_minute_at_120_second_freshness_limit() -> None:
    now = datetime(2026, 7, 23, 10, 5, tzinfo=HK)
    minute_time = now - timedelta(seconds=120)
    provider = StubStrictProvider(
        quotes=[_quote("01347.HK", now)],
        minute_rows=_minutes("01347.HK", minute_time),
    )

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch(
        ["01347.HK"],
        minute_time,
        now,
    )

    assert batch.freshness_by_symbol["01347.HK"].state == "LIVE"


def test_gateway_reports_only_internal_regular_session_gaps() -> None:
    now = datetime(2026, 7, 23, 9, 32, 30, tzinfo=HK)
    provider = StubStrictProvider(
        quotes=[_quote("01347.HK", now)],
        minute_rows=_minutes(
            "01347.HK",
            datetime(2026, 7, 23, 9, 30, tzinfo=HK),
            datetime(2026, 7, 23, 9, 32, tzinfo=HK),
        ),
    )

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch(
        ["01347.HK"],
        datetime(2026, 7, 23, 9, 30, tzinfo=HK),
        now,
    )

    assert batch.freshness_by_symbol["01347.HK"].state == "STALE_DATA"
    assert batch.freshness_by_symbol["01347.HK"].reason == "SESSION_GAP"
    assert batch.gap_details["01347.HK"] == [datetime(2026, 7, 23, 9, 31)]


def test_hk_lunch_break_is_not_reported_as_gap() -> None:
    now = datetime(2026, 7, 23, 13, 1, 30, tzinfo=HK)
    provider = StubStrictProvider(
        quotes=[_quote("01347.HK", now)],
        minute_rows=_minutes(
            "01347.HK",
            datetime(2026, 7, 23, 11, 59, tzinfo=HK),
            datetime(2026, 7, 23, 13, 0, tzinfo=HK),
            datetime(2026, 7, 23, 13, 1, tzinfo=HK),
        ),
    )

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch(
        ["01347.HK"],
        datetime(2026, 7, 23, 11, 59, tzinfo=HK),
        now,
    )

    assert batch.freshness_by_symbol["01347.HK"].state == "LIVE"
    assert batch.freshness_by_symbol["01347.HK"].reason is None
    assert batch.gap_details["01347.HK"] == []


def test_expected_minutes_match_lower_layer_sessions_and_trading_days() -> None:
    thursday = datetime(2026, 7, 23).date()
    saturday = datetime(2026, 7, 25).date()

    assert market_session_policy("600519.SH").timezone == "Asia/Shanghai"
    assert market_session_policy("01347.HK").timezone == "Asia/Hong_Kong"
    assert market_session_policy("INTC.US").timezone == "America/New_York"

    hk_minutes = expected_minutes("01347.HK", thursday)
    assert datetime(2026, 7, 23, 9, 30) in hk_minutes
    assert datetime(2026, 7, 23, 11, 59) in hk_minutes
    assert datetime(2026, 7, 23, 12, 0) not in hk_minutes
    assert datetime(2026, 7, 23, 13, 0) in hk_minutes
    assert datetime(2026, 7, 23, 15, 59) in hk_minutes
    assert datetime(2026, 7, 23, 16, 0) not in hk_minutes
    assert expected_minutes("INTC.US", saturday) == set()


def test_pre_market_and_after_hours_do_not_create_gaps_or_staleness() -> None:
    for now in (
        datetime(2026, 7, 23, 9, 29, tzinfo=US),
        datetime(2026, 7, 23, 16, 1, tzinfo=US),
    ):
        provider = StubStrictProvider(quotes=[], minute_rows=pl.DataFrame())

        batch = WebStockMonitorGateway(provider, now_fn=lambda now=now: now).fetch(
            ["INTC.US"],
            datetime(2026, 7, 23, 9, 0, tzinfo=US),
            now,
        )

        assert batch.freshness_by_symbol["INTC.US"].state == "LIVE"
        assert batch.gap_details["INTC.US"] == []


def test_future_regular_minutes_are_not_expected_or_reported_as_gaps() -> None:
    now = datetime(2026, 7, 23, 10, 0, 30, tzinfo=HK)
    provider = StubStrictProvider(
        quotes=[_quote("01347.HK", now)],
        minute_rows=_minutes(
            "01347.HK",
            datetime(2026, 7, 23, 10, 0, tzinfo=HK),
            datetime(2026, 7, 23, 10, 2, tzinfo=HK),
        ),
    )

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch(
        ["01347.HK"],
        datetime(2026, 7, 23, 10, 0, tzinfo=HK),
        datetime(2026, 7, 23, 10, 5, tzinfo=HK),
    )

    assert batch.freshness_by_symbol["01347.HK"].state == "LIVE"
    assert batch.gap_details["01347.HK"] == []
