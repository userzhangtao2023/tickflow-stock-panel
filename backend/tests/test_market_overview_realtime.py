from datetime import date

import polars as pl

from app.services import market_overview_builder as builder


class _Screener:
    def __init__(self, repo, asset_type: str = "stock", market: str = "cn") -> None:
        assert market == "us"

    def _load_enriched_for_date(self, target_date: date) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "symbol": ["AAPL.US", "MSFT.US"],
                "name": ["Apple", "Microsoft"],
                "close": [100.0, 200.0],
                "change_pct": [0.01, -0.01],
                "amount": [100.0, 200.0],
                "volume": [10.0, 20.0],
                "ma5": [105.0, 195.0],
            }
        )


class _Dimensions:
    def get_market_concepts(self, market: str) -> dict:
        return {"rows": []}

    def get_market_industries(self, market: str) -> dict:
        return {"rows": []}


def test_latest_us_overview_aggregates_realtime_price_amount_and_computed_change(monkeypatch) -> None:
    class RealtimeProvider:
        def get_realtime(self, universes=None, symbols=None):
            assert set(symbols) == {"AAPL.US", "MSFT.US"}
            return [
                {
                    "symbol": "AAPL.US",
                    "market": "us",
                    "last_price": 110.0,
                    "prev_close": 100.0,
                    "change_pct": None,
                    "volume": 99.0,
                    "amount": 999.0,
                },
                {
                    "symbol": "MSFT.US",
                    "market": "us",
                    "last_price": 190.0,
                    "prev_close": 200.0,
                    "change_pct": None,
                    "volume": 88.0,
                    "amount": 888.0,
                },
            ]

    monkeypatch.setattr(builder, "ScreenerService", _Screener)
    monkeypatch.setattr(builder, "market_latest_date", lambda repo, market: date(2026, 7, 17))

    result = builder.build_market_overview(
        object(),
        market="us",
        realtime_provider=RealtimeProvider(),
        dimension_provider=_Dimensions(),
    )

    assert result["breadth"]["up"] == 1
    assert result["breadth"]["down"] == 1
    assert result["amount"]["total"] == 1887.0
    assert result["top_gainers"][0]["symbol"] == "AAPL.US"
    assert result["top_gainers"][0]["close"] == 110.0
    assert result["top_gainers"][0]["change_pct"] == 0.1
    assert result["turnover_leaders"][0]["amount"] == 999.0


def test_historical_us_overview_does_not_read_realtime_provider(monkeypatch) -> None:
    class RealtimeProvider:
        def get_realtime(self, universes=None, symbols=None):
            raise AssertionError("historical overview must not read realtime quotes")

    monkeypatch.setattr(builder, "ScreenerService", _Screener)

    result = builder.build_market_overview(
        object(),
        market="us",
        as_of=date(2026, 7, 17),
        realtime_provider=RealtimeProvider(),
        dimension_provider=_Dimensions(),
    )

    assert result["amount"]["total"] == 300.0
    assert result["top_gainers"][0]["close"] == 100.0
