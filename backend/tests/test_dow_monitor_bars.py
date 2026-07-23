from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from app.services.dow_monitor_bars import TimeframeBars, build_timeframes


def _minute_rows(symbol: str, zone: str, values: list[tuple[str, float]]) -> pl.DataFrame:
    local_zone = ZoneInfo(zone)
    timestamps = [
        datetime.fromisoformat(timestamp).replace(tzinfo=local_zone).replace(tzinfo=None)
        for timestamp, _ in values
    ]
    opens = [price for _, price in values]
    return pl.DataFrame(
        {
            "symbol": [symbol] * len(values),
            "datetime": timestamps,
            "open": opens,
            "high": [price + 1.0 for price in opens],
            "low": [price - 1.0 for price in opens],
            "close": [price + 0.5 for price in opens],
            "volume": [10.0] * len(values),
            "amount": [100.0] * len(values),
            "source": ["webstock"] * len(values),
        }
    )


def _daily_rows(symbol: str) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": [symbol, symbol],
            "date": [date(2026, 7, 22), date(2026, 7, 23)],
            "open": [90.0, 999.0],
            "high": [95.0, 999.0],
            "low": [89.0, 999.0],
            "close": [94.0, 999.0],
            "volume": [1_000.0, 999.0],
            "amount": [93_000.0, 999.0],
        }
    )


@pytest.mark.parametrize(
    ("symbol", "zone", "session_values", "expected_starts"),
    [
        (
            "600519.SH",
            "Asia/Shanghai",
            [
                ("2026-07-23T09:30:00", 10.0),
                ("2026-07-23T11:29:00", 11.0),
                ("2026-07-23T12:59:00", 999.0),
                ("2026-07-23T13:00:00", 12.0),
                ("2026-07-23T14:59:00", 13.0),
            ],
            ["09:30", "11:25", "13:00", "14:55"],
        ),
        (
            "01347.HK",
            "Asia/Hong_Kong",
            [
                ("2026-07-23T09:30:00", 10.0),
                ("2026-07-23T11:59:00", 11.0),
                ("2026-07-23T12:30:00", 999.0),
                ("2026-07-23T13:00:00", 12.0),
                ("2026-07-23T15:59:00", 13.0),
            ],
            ["09:30", "11:55", "13:00", "15:55"],
        ),
        (
            "INTC.US",
            "America/New_York",
            [
                ("2026-07-23T08:00:00", 999.0),
                ("2026-07-23T09:30:00", 10.0),
                ("2026-07-23T15:59:00", 11.0),
                ("2026-07-23T16:01:00", 999.0),
            ],
            ["09:30", "15:55"],
        ),
    ],
)
def test_five_minute_buckets_never_cross_or_escape_regular_sessions(
    symbol: str,
    zone: str,
    session_values: list[tuple[str, float]],
    expected_starts: list[str],
) -> None:
    now = datetime(2026, 7, 23, 16, 5, tzinfo=ZoneInfo(zone))

    frames = build_timeframes(
        symbol,
        _minute_rows(symbol, zone, session_values),
        _daily_rows(symbol),
        now,
    )

    assert [bar["timestamp"][11:16] for bar in frames["5m"].all_bars] == expected_starts
    assert all(bar["open"] != 999.0 for bar in frames["5m"].all_bars)


def test_all_intraday_timeframes_derive_from_the_same_normalized_minutes() -> None:
    rows = _minute_rows(
        "01347.HK",
        "Asia/Hong_Kong",
        [
            ("2026-07-23T09:30:00", 10.0),
            ("2026-07-23T09:34:00", 20.0),
            ("2026-07-23T09:44:00", 30.0),
            ("2026-07-23T09:59:00", 40.0),
            ("2026-07-23T10:29:00", 50.0),
        ],
    )

    frames = build_timeframes(
        "01347.HK",
        rows,
        _daily_rows("01347.HK"),
        datetime(2026, 7, 23, 10, 30, tzinfo=ZoneInfo("Asia/Hong_Kong")),
    )

    assert set(frames) == {"5m", "15m", "30m", "60m", "day"}
    assert [(bar["timestamp"][11:16], bar["volume"]) for bar in frames["15m"].all_bars] == [
        ("09:30", 30.0),
        ("09:45", 10.0),
        ("10:15", 10.0),
    ]
    assert [(bar["timestamp"][11:16], bar["volume"]) for bar in frames["30m"].all_bars] == [
        ("09:30", 40.0),
        ("10:00", 10.0),
    ]
    assert [(bar["timestamp"][11:16], bar["volume"]) for bar in frames["60m"].all_bars] == [
        ("09:30", 50.0),
    ]
    assert frames["60m"].all_bars[0] == {
        "timestamp": "2026-07-23T09:30:00+08:00",
        "open": 10.0,
        "high": 51.0,
        "low": 9.0,
        "close": 50.5,
        "volume": 50.0,
        "amount": 500.0,
    }


def test_current_bucket_is_forming_and_prior_buckets_are_completed() -> None:
    rows = _minute_rows(
        "01347.HK",
        "Asia/Hong_Kong",
        [
            ("2026-07-23T09:30:00", 10.0),
            ("2026-07-23T09:34:00", 11.0),
            ("2026-07-23T09:35:00", 12.0),
            ("2026-07-23T09:36:00", 13.0),
        ],
    )

    frame = build_timeframes(
        "01347.HK",
        rows,
        pl.DataFrame(),
        datetime(2026, 7, 23, 9, 36, 30, tzinfo=ZoneInfo("Asia/Hong_Kong")),
    )["5m"]

    assert isinstance(frame, TimeframeBars)
    assert frame.completion == "FORMING"
    assert [bar["timestamp"][11:16] for bar in frame.completed] == ["09:30"]
    assert frame.forming["timestamp"] == "2026-07-23T09:35:00+08:00"
    assert frame.all_bars == [*frame.completed, frame.forming]


def test_last_bucket_is_final_once_its_session_capped_end_is_reached() -> None:
    rows = _minute_rows(
        "01347.HK",
        "Asia/Hong_Kong",
        [
            ("2026-07-23T11:29:00", 10.0),
            ("2026-07-23T11:30:00", 11.0),
            ("2026-07-23T11:59:00", 12.0),
        ],
    )

    before_lunch = build_timeframes(
        "01347.HK",
        rows,
        pl.DataFrame(),
        datetime(2026, 7, 23, 12, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
    )

    assert before_lunch["60m"].completion == "FINAL"
    assert before_lunch["60m"].forming["timestamp"] == "2026-07-23T11:30:00+08:00"
    assert before_lunch["60m"].completed == before_lunch["60m"].all_bars


@pytest.mark.parametrize(
    ("symbol", "zone", "morning_last", "afternoon_first", "expected_starts"),
    [
        (
            "600519.SH",
            "Asia/Shanghai",
            "2026-07-23T11:29:00",
            "2026-07-23T13:00:00",
            ["10:30", "13:00"],
        ),
        (
            "01347.HK",
            "Asia/Hong_Kong",
            "2026-07-23T11:59:00",
            "2026-07-23T13:00:00",
            ["11:30", "13:00"],
        ),
    ],
)
def test_sixty_minute_buckets_end_at_lunch_and_restart_at_afternoon_session(
    symbol: str,
    zone: str,
    morning_last: str,
    afternoon_first: str,
    expected_starts: list[str],
) -> None:
    frame = build_timeframes(
        symbol,
        _minute_rows(
            symbol,
            zone,
            [(morning_last, 10.0), (afternoon_first, 20.0)],
        ),
        pl.DataFrame(),
        datetime(2026, 7, 23, 13, 1, tzinfo=ZoneInfo(zone)),
    )["60m"]

    assert [bar["timestamp"][11:16] for bar in frame.all_bars] == expected_starts
    assert [bar["volume"] for bar in frame.all_bars] == [10.0, 10.0]
    assert frame.completion == "FORMING"


def test_current_daily_bar_replaces_stored_today_with_minute_ohlcv() -> None:
    frames = build_timeframes(
        "01347.HK",
        _minute_rows(
            "01347.HK",
            "Asia/Hong_Kong",
            [
                ("2026-07-23T09:30:00", 100.0),
                ("2026-07-23T10:00:00", 105.0),
                ("2026-07-23T10:05:00", 102.0),
            ],
        ),
        _daily_rows("01347.HK"),
        datetime(2026, 7, 23, 10, 5, 30, tzinfo=ZoneInfo("Asia/Hong_Kong")),
    )

    day = frames["day"]
    assert day.completion == "FORMING"
    assert [bar["timestamp"] for bar in day.completed] == ["2026-07-22"]
    assert day.forming == {
        "timestamp": "2026-07-23",
        "open": 100.0,
        "high": 106.0,
        "low": 99.0,
        "close": 102.5,
        "volume": 30.0,
        "amount": 300.0,
    }
    assert day.source_timestamp == datetime(2026, 7, 23, 10, 5, tzinfo=ZoneInfo("Asia/Hong_Kong"))


def test_current_daily_bar_combines_morning_and_afternoon_sessions() -> None:
    day = build_timeframes(
        "01347.HK",
        _minute_rows(
            "01347.HK",
            "Asia/Hong_Kong",
            [
                ("2026-07-23T09:30:00", 100.0),
                ("2026-07-23T11:59:00", 105.0),
                ("2026-07-23T13:00:00", 90.0),
                ("2026-07-23T15:00:00", 110.0),
            ],
        ),
        pl.DataFrame(),
        datetime(2026, 7, 23, 15, 1, tzinfo=ZoneInfo("Asia/Hong_Kong")),
    )["day"]

    assert day.forming == {
        "timestamp": "2026-07-23",
        "open": 100.0,
        "high": 111.0,
        "low": 89.0,
        "close": 110.5,
        "volume": 40.0,
        "amount": 400.0,
    }


def test_current_daily_bar_is_final_after_regular_session_close() -> None:
    day = build_timeframes(
        "01347.HK",
        _minute_rows(
            "01347.HK",
            "Asia/Hong_Kong",
            [("2026-07-23T15:59:00", 100.0)],
        ),
        _daily_rows("01347.HK"),
        datetime(2026, 7, 23, 16, 0, tzinfo=ZoneInfo("Asia/Hong_Kong")),
    )["day"]

    assert day.completion == "FINAL"
    assert day.completed == day.all_bars
    assert day.all_bars[-1]["timestamp"] == "2026-07-23"


@pytest.mark.parametrize(
    ("symbol", "zone", "close_time", "expected_start"),
    [
        ("600519.SH", "Asia/Shanghai", "2026-07-23T15:00:00", "14:55"),
        ("01347.HK", "Asia/Hong_Kong", "2026-07-23T16:00:00", "15:55"),
    ],
)
def test_cn_and_hk_isolated_close_minute_merges_into_last_regular_bucket(
    symbol: str,
    zone: str,
    close_time: str,
    expected_start: str,
) -> None:
    close = datetime.fromisoformat(close_time).replace(tzinfo=ZoneInfo(zone))
    previous = (close.replace(tzinfo=None) - timedelta(minutes=1)).isoformat()
    frame = build_timeframes(
        symbol,
        _minute_rows(
            symbol,
            zone,
            [(previous, 100.0), (close_time, 120.0)],
        ),
        pl.DataFrame(),
        close,
    )["5m"]

    assert len(frame.all_bars) == 1
    assert frame.forming["timestamp"][11:16] == expected_start
    assert frame.forming["open"] == 100.0
    assert frame.forming["close"] == 120.5
    assert frame.forming["volume"] == 20.0
    assert frame.completion == "FINAL"


@pytest.mark.parametrize(
    ("as_of_utc", "expected_offset"),
    [
        (datetime(2026, 7, 23, 13, 35, tzinfo=UTC), "-04:00"),
        (datetime(2026, 1, 22, 14, 35, tzinfo=UTC), "-05:00"),
    ],
)
def test_us_daylight_saving_conversion_keeps_regular_session_local_anchor(
    as_of_utc: datetime,
    expected_offset: str,
) -> None:
    local = as_of_utc.astimezone(ZoneInfo("America/New_York"))
    frame = build_timeframes(
        "INTC.US",
        _minute_rows(
            "INTC.US",
            "America/New_York",
            [(local.replace(tzinfo=None).isoformat(), 100.0)],
        ),
        pl.DataFrame(),
        as_of_utc,
    )["5m"]

    assert frame.forming["timestamp"].endswith(expected_offset)
    assert frame.forming["timestamp"][11:16] == "09:35"
    assert frame.completion == "FORMING"
