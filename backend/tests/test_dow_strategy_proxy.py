from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dow_strategy


def test_pool_and_backtest_proxy_to_longbridge(monkeypatch):
    calls = []

    class Response:
        def __init__(self, payload): self._payload = payload
        def raise_for_status(self): return None
        def json(self): return self._payload

    def fake_get(url, params=None, timeout=None):
        calls.append(("get", url, params))
        return Response({"stocks": [{"symbol": "700.HK", "triggerTimeframes": ["30m"]}]})

    def fake_post(url, json=None, timeout=None):
        calls.append(("post", url, json))
        return Response({"metrics": {"tradeCount": 1}, "trades": []})

    monkeypatch.setenv("LONGBRIDGE_API_URL", "http://longbridge")
    monkeypatch.setattr(dow_strategy.httpx, "get", fake_get)
    monkeypatch.setattr(dow_strategy.httpx, "post", fake_post)
    app = FastAPI(); app.include_router(dow_strategy.router)
    client = TestClient(app)

    pool = client.get("/api/dow-strategy/pool?market=hk&limit=20")
    assert pool.status_code == 200
    assert pool.json()["stocks"][0]["symbol"] == "700.HK"
    result = client.post("/api/dow-strategy/backtest", json={"market": "hk", "symbols": ["700.HK"]})
    assert result.status_code == 200
    assert calls[0][2] == {"market": "hk", "limit": 20, "strategy": "dow_trend"}
    assert calls[1][1] == "http://longbridge/api/dow-strategy/backtest"
