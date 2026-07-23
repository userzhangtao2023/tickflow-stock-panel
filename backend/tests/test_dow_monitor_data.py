from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from app.services import dow_monitor_data
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


def test_gateway_rejects_naive_now_before_accessing_provider() -> None:
    provider = StubStrictProvider(quotes=[], minute_rows=pl.DataFrame())
    gateway = WebStockMonitorGateway(
        provider,
        now_fn=lambda: datetime(2026, 7, 23, 10, 0),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        gateway.fetch(
            ["01347.HK"],
            datetime(2026, 7, 23, 9, 30, tzinfo=HK),
            datetime(2026, 7, 23, 10, 0, tzinfo=HK),
        )

    assert provider.calls == []


def test_gateway_normalizes_and_deduplicates_nonempty_symbols() -> None:
    now = datetime(2026, 7, 26, 10, 0, tzinfo=UTC)
    provider = StubStrictProvider(quotes=[], minute_rows=pl.DataFrame())

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch(
        [" 01347.hk ", "", "01347.HK", " intc.us ", "  "],
        now,
        now,
    )

    assert provider.calls == [
        ("realtime", ["01347.HK", "INTC.US"]),
        ("minute", ["01347.HK", "INTC.US"], now, now),
    ]
    assert list(batch.freshness_by_symbol) == ["01347.HK", "INTC.US"]


def test_gateway_empty_symbols_do_not_access_provider() -> None:
    now = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
    provider = StubStrictProvider(quotes=[], minute_rows=pl.DataFrame())

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch(
        ["", "  "],
        now,
        now,
    )

    assert provider.calls == []
    assert batch.quotes == []
    assert batch.minute_rows.is_empty()
    assert batch.source_timestamp is None
    assert batch.freshness_by_symbol == {}
    assert batch.gap_details == {}


@pytest.mark.parametrize(
    ("now", "expected_state"),
    [
        (datetime(2026, 7, 23, 9, 29, 59, tzinfo=ZoneInfo("Asia/Shanghai")), "LIVE"),
        (datetime(2026, 7, 23, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")), "STALE_DATA"),
        (datetime(2026, 7, 23, 11, 29, 59, tzinfo=ZoneInfo("Asia/Shanghai")), "STALE_DATA"),
        (datetime(2026, 7, 23, 11, 30, tzinfo=ZoneInfo("Asia/Shanghai")), "LIVE"),
        (datetime(2026, 7, 23, 12, 59, 59, tzinfo=ZoneInfo("Asia/Shanghai")), "LIVE"),
        (datetime(2026, 7, 23, 13, 0, tzinfo=ZoneInfo("Asia/Shanghai")), "STALE_DATA"),
        (datetime(2026, 7, 23, 14, 59, 59, tzinfo=ZoneInfo("Asia/Shanghai")), "STALE_DATA"),
        (datetime(2026, 7, 23, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")), "LIVE"),
    ],
)
def test_cn_open_close_and_lunch_boundaries(
    now: datetime,
    expected_state: str,
) -> None:
    provider = StubStrictProvider(quotes=[], minute_rows=pl.DataFrame())

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch(
        ["600519.SH"],
        now,
        now,
    )

    assert batch.freshness_by_symbol["600519.SH"].state == expected_state


@pytest.mark.parametrize(
    ("now_utc", "expected_state"),
    [
        (datetime(2026, 7, 23, 13, 29, 59, tzinfo=UTC), "LIVE"),
        (datetime(2026, 7, 23, 13, 30, tzinfo=UTC), "STALE_DATA"),
        (datetime(2026, 7, 23, 19, 59, 59, tzinfo=UTC), "STALE_DATA"),
        (datetime(2026, 7, 23, 20, 0, tzinfo=UTC), "LIVE"),
        (datetime(2026, 1, 22, 14, 29, 59, tzinfo=UTC), "LIVE"),
        (datetime(2026, 1, 22, 14, 30, tzinfo=UTC), "STALE_DATA"),
        (datetime(2026, 1, 22, 20, 59, 59, tzinfo=UTC), "STALE_DATA"),
        (datetime(2026, 1, 22, 21, 0, tzinfo=UTC), "LIVE"),
    ],
)
def test_us_open_close_respects_daylight_saving_time(
    now_utc: datetime,
    expected_state: str,
) -> None:
    provider = StubStrictProvider(quotes=[], minute_rows=pl.DataFrame())

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now_utc).fetch(
        ["INTC.US"],
        now_utc,
        now_utc,
    )

    assert batch.freshness_by_symbol["INTC.US"].state == expected_state


def test_cross_weekday_blank_date_is_not_assumed_to_be_a_trading_day() -> None:
    now = datetime(2026, 7, 22, 9, 32, 30, tzinfo=HK)
    provider = StubStrictProvider(
        quotes=[_quote("01347.HK", now)],
        minute_rows=_minutes(
            "01347.HK",
            datetime(2026, 7, 20, 15, 59, tzinfo=HK),
            datetime(2026, 7, 22, 9, 30, tzinfo=HK),
            datetime(2026, 7, 22, 9, 31, tzinfo=HK),
            datetime(2026, 7, 22, 9, 32, tzinfo=HK),
        ),
    )

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch(
        ["01347.HK"],
        datetime(2026, 7, 20, 15, 59, tzinfo=HK),
        now,
    )

    assert batch.freshness_by_symbol["01347.HK"].state == "LIVE"
    assert batch.gap_details["01347.HK"] == []


def test_fetch_since_uses_one_query_but_independent_symbol_windows() -> None:
    now = datetime(2026, 7, 23, 10, 2, 30, tzinfo=HK)
    hot_symbol = "01347.HK"
    cold_symbol = "00700.HK"
    rows = pl.concat(
        [
            _minutes(
                hot_symbol,
                datetime(2026, 7, 23, 9, 58, tzinfo=HK),
                datetime(2026, 7, 23, 10, 0, tzinfo=HK),
                datetime(2026, 7, 23, 10, 1, tzinfo=HK),
                datetime(2026, 7, 23, 10, 2, tzinfo=HK),
            ),
            _minutes(
                cold_symbol,
                datetime(2026, 7, 23, 9, 58, tzinfo=HK),
                datetime(2026, 7, 23, 10, 0, tzinfo=HK),
                datetime(2026, 7, 23, 10, 1, tzinfo=HK),
                datetime(2026, 7, 23, 10, 2, tzinfo=HK),
            ),
        ]
    )
    provider = StubStrictProvider(
        quotes=[_quote(hot_symbol, now), _quote(cold_symbol, now)],
        minute_rows=rows,
    )
    hot_start = datetime(2026, 7, 23, 10, 0, tzinfo=HK)
    cold_start = datetime(2026, 7, 23, 9, 58, tzinfo=HK)

    batch = WebStockMonitorGateway(provider, now_fn=lambda: now).fetch_since(
        {
            " 01347.hk ": hot_start + timedelta(minutes=1),
            hot_symbol: hot_start,
            cold_symbol: cold_start,
        },
        now,
    )

    assert provider.calls == [
        ("realtime", [hot_symbol, cold_symbol]),
        ("minute", [hot_symbol, cold_symbol], cold_start, now),
    ]
    assert batch.freshness_by_symbol[hot_symbol].state == "LIVE"
    assert batch.gap_details[hot_symbol] == []
    assert batch.freshness_by_symbol[cold_symbol].reason == "SESSION_GAP"
    assert batch.gap_details[cold_symbol] == [datetime(2026, 7, 23, 9, 59)]


def test_fresh_fetch_window_is_not_coupled_to_incomplete_prior_history() -> None:
    symbol = "01347.HK"
    now = datetime(2026, 7, 23, 10, 2, 30, tzinfo=HK)
    current_start = datetime(2026, 7, 23, 10, 0, tzinfo=HK)
    rows = _minutes(
        symbol,
        datetime(2026, 7, 22, 9, 30, tzinfo=HK),
        datetime(2026, 7, 22, 9, 32, tzinfo=HK),
        datetime(2026, 7, 23, 10, 0, tzinfo=HK),
        datetime(2026, 7, 23, 10, 1, tzinfo=HK),
        datetime(2026, 7, 23, 10, 2, tzinfo=HK),
    )
    provider = StubStrictProvider(
        quotes=[_quote(symbol, now)],
        minute_rows=rows,
    )
    gateway = WebStockMonitorGateway(provider, now_fn=lambda: now)

    batch = gateway.fetch_since({symbol: current_start}, now)
    history = gateway.load_history([symbol], now)

    assert batch.freshness_by_symbol[symbol].state == "LIVE"
    assert batch.gap_details[symbol] == []
    coverage = history.coverage_by_symbol[symbol]
    assert coverage.latest_prior_session_date == datetime(2026, 7, 22).date()
    assert coverage.latest_prior_session_complete is False
    assert coverage.state == "INCOMPLETE"
    assert coverage.reason == "LATEST_PRIOR_SESSION_INCOMPLETE"
    assert history.minute_rows.height == rows.height
    assert provider.calls == [
        ("realtime", [symbol]),
        ("minute", [symbol], current_start, now),
        ("minute", [symbol], None, now),
    ]


def test_cn_history_finds_complete_latest_session_before_long_holiday() -> None:
    symbol = "600519.SH"
    zone = ZoneInfo("Asia/Shanghai")
    session_date = datetime(2026, 9, 30).date()
    end = datetime(2026, 10, 9, 10, 0, tzinfo=zone)
    values = [
        value.replace(tzinfo=zone) for value in sorted(expected_minutes(symbol, session_date))
    ]
    values.append(datetime(2026, 9, 30, 15, 0, tzinfo=zone))
    provider = StubStrictProvider(quotes=[], minute_rows=_minutes(symbol, *values))

    history = WebStockMonitorGateway(provider, now_fn=lambda: end).load_history(
        [symbol],
        end,
    )

    coverage = history.coverage_by_symbol[symbol]
    assert coverage.earliest_timestamp == datetime(2026, 9, 30, 9, 30)
    assert coverage.latest_timestamp == datetime(2026, 9, 30, 15, 0)
    assert coverage.latest_prior_session_date == session_date
    assert coverage.latest_prior_session_complete is True
    assert coverage.state == "COMPLETE"
    assert coverage.reason is None
    assert provider.calls == [("minute", [symbol], None, end)]


def test_hk_history_completeness_respects_lunch_and_ignores_close_rows() -> None:
    symbol = "01347.HK"
    session_date = datetime(2026, 7, 22).date()
    end = datetime(2026, 7, 23, 9, 0, tzinfo=HK)
    values = [value.replace(tzinfo=HK) for value in sorted(expected_minutes(symbol, session_date))]
    values.extend(
        [
            datetime(2026, 7, 22, 12, 0, tzinfo=HK),
            datetime(2026, 7, 22, 16, 0, tzinfo=HK),
        ]
    )
    provider = StubStrictProvider(quotes=[], minute_rows=_minutes(symbol, *values))

    history = WebStockMonitorGateway(provider, now_fn=lambda: end).load_history(
        [symbol],
        end,
    )

    coverage = history.coverage_by_symbol[symbol]
    assert coverage.latest_prior_session_date == session_date
    assert coverage.latest_prior_session_complete is True
    assert coverage.state == "COMPLETE"


def test_hk_history_excludes_same_day_rows_after_exact_end() -> None:
    symbol = "01347.HK"
    end = datetime(2026, 7, 23, 10, 0, tzinfo=HK)
    provider = StubStrictProvider(
        quotes=[],
        minute_rows=_minutes(
            symbol,
            datetime(2026, 7, 23, 9, 59, tzinfo=HK),
            datetime(2026, 7, 23, 15, 0, tzinfo=HK),
        ),
    )

    history = WebStockMonitorGateway(provider, now_fn=lambda: end).load_history(
        [symbol],
        end,
    )

    assert provider.calls == [("minute", [symbol], None, end)]
    assert history.minute_rows.get_column("datetime").to_list() == [datetime(2026, 7, 23, 9, 59)]
    assert history.coverage_by_symbol[symbol].latest_timestamp == datetime(
        2026,
        7,
        23,
        9,
        59,
    )


def test_us_history_completeness_uses_dst_market_local_session() -> None:
    symbol = "INTC.US"
    utc_values = [
        datetime(2026, 3, 9, 13, 30, tzinfo=UTC) + timedelta(minutes=offset)
        for offset in range(390)
    ]
    minute_rows = _minutes(symbol, *utc_values).with_columns(pl.Series("datetime", utc_values))
    end = datetime(2026, 3, 10, 13, 0, tzinfo=UTC)
    provider = StubStrictProvider(quotes=[], minute_rows=minute_rows)

    history = WebStockMonitorGateway(provider, now_fn=lambda: end).load_history(
        [symbol],
        end,
    )

    coverage = history.coverage_by_symbol[symbol]
    assert coverage.earliest_timestamp == datetime(2026, 3, 9, 9, 30)
    assert coverage.latest_timestamp == datetime(2026, 3, 9, 15, 59)
    assert coverage.latest_prior_session_date == datetime(2026, 3, 9).date()
    assert coverage.latest_prior_session_complete is True


def test_us_history_filters_exact_end_across_utc_local_date_boundary() -> None:
    symbol = "INTC.US"
    end = datetime(2026, 7, 24, 0, 0, tzinfo=UTC)
    utc_values = [
        datetime(2026, 7, 23, 19, 59, tzinfo=UTC),
        datetime(2026, 7, 24, 0, 30, tzinfo=UTC),
    ]
    minute_rows = _minutes(symbol, *utc_values).with_columns(pl.Series("datetime", utc_values))
    provider = StubStrictProvider(quotes=[], minute_rows=minute_rows)

    history = WebStockMonitorGateway(provider, now_fn=lambda: end).load_history(
        [symbol],
        end,
    )

    assert provider.calls == [("minute", [symbol], None, end)]
    assert history.minute_rows.get_column("datetime").to_list() == [utc_values[0]]
    assert history.coverage_by_symbol[symbol].latest_timestamp == datetime(
        2026,
        7,
        23,
        15,
        59,
    )


def test_history_normalizes_symbols_and_reports_no_prior_session() -> None:
    end = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
    provider = StubStrictProvider(quotes=[], minute_rows=pl.DataFrame())

    history = WebStockMonitorGateway(provider, now_fn=lambda: end).load_history(
        [" aapl.us ", "AAPL.US", ""],
        end,
    )

    assert provider.calls == [("minute", ["AAPL.US"], None, end)]
    coverage = history.coverage_by_symbol["AAPL.US"]
    assert coverage.earliest_timestamp is None
    assert coverage.latest_timestamp is None
    assert coverage.latest_prior_session_date is None
    assert coverage.latest_prior_session_complete is False
    assert coverage.state == "INCOMPLETE"
    assert coverage.reason == "NO_PRIOR_SESSION"


def test_history_and_fetch_since_empty_inputs_do_not_access_provider() -> None:
    end = datetime(2026, 7, 23, 10, 0, tzinfo=UTC)
    provider = StubStrictProvider(quotes=[], minute_rows=pl.DataFrame())
    gateway = WebStockMonitorGateway(provider, now_fn=lambda: end)

    history = gateway.load_history(["", "  "], end)
    batch = gateway.fetch_since({}, end)

    assert history.minute_rows.is_empty()
    assert history.coverage_by_symbol == {}
    assert batch.minute_rows.is_empty()
    assert batch.freshness_by_symbol == {}
    assert provider.calls == []


def test_history_bootstrap_calls_longbridge_once_per_normalized_symbol(
    monkeypatch,
) -> None:
    calls: list[tuple[str, dict, float]] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"bars": [{"time": "2026-07-22T15:59:00+08:00"}]}

    def fake_get(url: str, *, params: dict, timeout: float):
        calls.append((url, params, timeout))
        return Response()

    monkeypatch.setenv("LONGBRIDGE_API_URL", "http://longbridge:19912/")
    monkeypatch.setattr(dow_monitor_data.httpx, "get", fake_get)
    provider = StubStrictProvider(quotes=[], minute_rows=pl.DataFrame())

    WebStockMonitorGateway(provider).bootstrap_history(
        [" 01347.HK ", "01347.HK"],
    )

    assert calls == [(
        "http://longbridge:19912/api/stocks/01347.HK/klines",
        {"period": "1m", "limit": 1000},
        20.0,
    )]


@pytest.mark.parametrize(
    "operation",
    [
        lambda gateway: gateway.fetch_since(
            {"01347.HK": datetime(2026, 7, 23, 9, 30)},
            datetime(2026, 7, 23, 10, 0, tzinfo=HK),
        ),
        lambda gateway: gateway.fetch_since(
            {"01347.HK": datetime(2026, 7, 23, 9, 30, tzinfo=HK)},
            datetime(2026, 7, 23, 10, 0),
        ),
        lambda gateway: gateway.load_history(
            ["01347.HK"],
            datetime(2026, 7, 23, 10, 0),
        ),
    ],
)
def test_history_capabilities_reject_naive_bounds_before_provider_access(operation) -> None:
    aware_now = datetime(2026, 7, 23, 10, 0, tzinfo=HK)
    provider = StubStrictProvider(quotes=[], minute_rows=pl.DataFrame())
    gateway = WebStockMonitorGateway(provider, now_fn=lambda: aware_now)

    with pytest.raises(ValueError, match="timezone-aware"):
        operation(gateway)

    assert provider.calls == []
