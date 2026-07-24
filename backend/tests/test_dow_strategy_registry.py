from pathlib import Path
from types import SimpleNamespace

from app.api.strategy import get_strategy, list_strategies
from app.strategy.engine import StrategyEngine


BUILTIN_DIR = Path(__file__).parents[1] / "app" / "strategy" / "builtin"


def _request(engine: StrategyEngine, tmp_path: Path) -> SimpleNamespace:
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        repo=repo,
        strategy_engine=engine,
    )))


def test_dow_trend_is_registered_as_builtin_stock_strategy(tmp_path):
    engine = StrategyEngine([BUILTIN_DIR])

    strategy = engine.get("dow_trend")
    assert strategy.meta["name"] == "道氏趋势 · 多周期"
    assert strategy.meta["asset_types"] == ["stock"]
    assert strategy.meta["timeframes"] == ["1d"]
    assert strategy.source == "builtin"
    assert strategy.execution_backend == "external"
    assert strategy.file_path == BUILTIN_DIR / "dow_trend.py"

    request = _request(engine, tmp_path)
    listed = list_strategies(request, asset_type="stock", timeframe="1d")
    assert [item["id"] for item in listed["strategies"]].count("dow_trend") == 1
    assert get_strategy("dow_trend", request)["source"] == "builtin"
