from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from app.services.dow_monitor_indicators import (
    DOW_CHART_INDICATOR_FIELDS,
    enrich_dow_chart_bars,
)


def _bars(timeframe: str, count: int = 80) -> list[dict]:
    start = datetime(2026, 1, 2, 9, 30, tzinfo=UTC)
    step = timedelta(days=1) if timeframe == "day" else timedelta(minutes=5)
    rows = []
    for index in range(count):
        close = 100 + index * 0.15 + math.sin(index / 3)
        rows.append(
            {
                "index": index,
                "timestamp": (start + index * step).isoformat(),
                "open": close - 0.2,
                "high": close + 0.8,
                "low": close - 0.7,
                "close": close,
                "volume": 1_000 + index * 17,
            }
        )
    return rows


@pytest.mark.parametrize("timeframe", ["5m", "day"])
def test_reuses_indicator_pipeline_for_finite_intraday_and_daily_chart_values(
    timeframe: str,
) -> None:
    bars = _bars(timeframe)
    original = [dict(bar) for bar in bars]

    enriched = enrich_dow_chart_bars("01347.HK", bars)

    assert bars == original
    assert len(enriched) == len(bars)
    assert {
        key: enriched[-1][key]
        for key in ("index", "timestamp", "open", "high", "low", "close", "volume")
    } == {
        key: bars[-1][key]
        for key in ("index", "timestamp", "open", "high", "low", "close", "volume")
    }
    for field in DOW_CHART_INDICATOR_FIELDS:
        assert field in enriched[-1]
        assert math.isfinite(enriched[-1][field])
