from pathlib import Path


def test_dow_trend_is_registered_as_builtin_stock_strategy():
    source = (Path(__file__).parents[1] / "app" / "api" / "strategy.py").read_text(encoding="utf-8")

    assert '"id": "dow_trend"' in source
    assert '"name": "道氏趋势 · 多周期"' in source
    assert '"source": "builtin"' in source
