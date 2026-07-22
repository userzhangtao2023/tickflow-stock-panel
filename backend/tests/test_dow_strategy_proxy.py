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


def test_scan_job_proxy_starts_and_reads_progress(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self): return None
        def json(self): return {"runId": "scan-hk-1", "status": "running", "completed": 3, "total": 100}

    monkeypatch.setenv("LONGBRIDGE_API_URL", "http://longbridge")
    monkeypatch.setattr(dow_strategy.httpx, "post", lambda url, json=None, timeout=None: calls.append(("post", url, json)) or Response())
    monkeypatch.setattr(dow_strategy.httpx, "get", lambda url, timeout=None: calls.append(("get", url)) or Response())
    app = FastAPI(); app.include_router(dow_strategy.router)
    client = TestClient(app)

    assert client.post("/api/dow-strategy/runs", json={"market": "hk"}).status_code == 200
    assert client.get("/api/dow-strategy/runs/scan-hk-1").json()["completed"] == 3
    assert calls == [
        ("post", "http://longbridge/api/dow-strategy/runs", {"market": "hk"}),
        ("get", "http://longbridge/api/dow-strategy/runs/scan-hk-1"),
    ]
