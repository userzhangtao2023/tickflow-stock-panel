from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dow_monitor
from app.services.dow_monitor_models import DowNotification, DowTimeframeState
from app.services.dow_monitor_service import DowMonitorService
from app.services.dow_monitor_store import DowMonitorStore

NOW = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)


class _UnusedGateway:
    pass


class _UnusedDowClient:
    pass


def _daily_loader(*_args):
    raise AssertionError("API handlers must not load market data")


def _service(tmp_path) -> DowMonitorService:
    return DowMonitorService(
        DowMonitorStore(tmp_path),
        _UnusedGateway(),
        _UnusedDowClient(),
        _daily_loader,
        now_fn=lambda: NOW,
    )


def _client(service: DowMonitorService) -> TestClient:
    app = FastAPI()
    app.state.dow_monitor_service = service
    app.include_router(dow_monitor.router)
    return TestClient(app)


def test_symbols_are_normalized_and_duplicate_add_is_idempotent(tmp_path) -> None:
    service = _service(tmp_path)
    client = _client(service)

    first = client.post("/api/dow-monitor/symbols", json={"symbol": " 01347.hk "})
    second = client.post("/api/dow-monitor/symbols", json={"symbol": "01347.HK"})

    assert first.status_code == 200
    assert first.json()["symbol"] == "01347.HK"
    assert second.status_code == 200
    assert len(client.get("/api/dow-monitor/symbols").json()["symbols"]) == 1


def test_symbols_reject_unsupported_suffix(tmp_path) -> None:
    client = _client(_service(tmp_path))

    response = client.post("/api/dow-monitor/symbols", json={"symbol": "BTC.CRYPTO"})

    assert response.status_code == 400


def test_patch_switch_persists_normalized_symbol(tmp_path) -> None:
    service = _service(tmp_path)
    client = _client(service)
    client.post("/api/dow-monitor/symbols", json={"symbol": "01347.HK"})

    response = client.patch("/api/dow-monitor/symbols/ 01347.hk ", json={"enabled": False})

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert service.store.list_symbols()[0].enabled is False


def test_market_filter_changes_response_only_not_enabled_state(tmp_path) -> None:
    service = _service(tmp_path)
    service.store.upsert_symbol("01347.HK", "hk", True)
    service.store.upsert_symbol("INTC.US", "us", True)
    client = _client(service)

    response = client.get("/api/dow-monitor/overview?market=hk")

    assert response.status_code == 200
    assert {item["market"] for item in response.json()["symbols"]} == {"hk"}
    assert next(item for item in service.store.list_symbols() if item.symbol == "INTC.US").enabled


def test_detail_validates_timeframe_and_preserves_long_term_sidecar(tmp_path) -> None:
    service = _service(tmp_path)
    service.store.upsert_symbol("01347.HK", "hk", True)
    service.store.save_state(
        DowTimeframeState(
            symbol="01347.HK",
            market="hk",
            timeframe="5m",
            freshness_state="LIVE",
            source_timestamp=NOW,
            snapshot={},
            chart={"longTerm": {"trendDirection": "UP", "operation": "持有"}},
            updated_at=NOW,
        )
    )
    client = _client(service)

    valid = client.get("/api/dow-monitor/01347.hk?timeframe=5m")
    invalid = client.get("/api/dow-monitor/01347.HK?timeframe=1m")

    assert valid.status_code == 200
    assert valid.json()["chart"]["longTerm"] == {
        "trendDirection": "UP",
        "operation": "持有",
    }
    assert invalid.status_code == 422


def test_notifications_read_and_status_expose_persisted_timestamps(tmp_path) -> None:
    service = _service(tmp_path)
    service.store.append_notification(
        DowNotification(
            notification_id="notification-1",
            event_key="event-1",
            symbol="01347.HK",
            market="hk",
            timeframe="5m",
            side="BUY",
            action_name="buy",
            shape_name="shape",
            triggered_at=NOW,
            trigger_price=12.3,
            snapshot_payload={"engine": {"longTerm": {"trendDirection": "UP"}}},
        )
    )
    client = _client(service)

    notifications = client.get("/api/dow-monitor/notifications?market=hk&unreadOnly=true")
    read = client.patch("/api/dow-monitor/notifications/notification-1/read")
    status = client.get("/api/dow-monitor/status")

    assert notifications.status_code == 200
    assert notifications.json()["notifications"][0]["triggered_at"] == "2026-07-23T08:00:00Z"
    assert read.status_code == 200
    assert read.json()["read_at"] is not None
    assert (
        client.get("/api/dow-monitor/notifications?unreadOnly=true").json()["notifications"] == []
    )
    assert status.status_code == 200
    assert set(status.json()) >= {
        "last_started_at",
        "last_completed_at",
        "last_success_at",
    }


def test_uninitialized_service_returns_503() -> None:
    app = FastAPI()
    app.include_router(dow_monitor.router)

    response = TestClient(app).get("/api/dow-monitor/status")

    assert response.status_code == 503


def test_lifecycle_starts_single_monitor_with_registered_clickhouse_provider(
    monkeypatch, tmp_path
) -> None:
    from app import main

    events: list[object] = []

    class FakeStore:
        def __init__(self, data_dir) -> None:
            events.append(("store", data_dir))

    class FakeGateway:
        def __init__(self, provider) -> None:
            events.append(("gateway", provider))

    class FakeClient:
        def __init__(self, endpoint) -> None:
            events.append(("client", endpoint))

    class FakeService:
        def __init__(self, store, gateway, client, daily_loader) -> None:
            self.store = store
            self.gateway = gateway
            self.client = client
            self.daily_loader = daily_loader
            self.started = 0

        async def start(self) -> None:
            self.started += 1
            events.append("start")

    provider = SimpleNamespace(get_daily=lambda *_args: "daily")
    app = SimpleNamespace(state=SimpleNamespace())
    monkeypatch.setattr(main, "DowMonitorStore", FakeStore, raising=False)
    monkeypatch.setattr(main, "WebStockMonitorGateway", FakeGateway, raising=False)
    monkeypatch.setattr(main, "LongbridgeDowClient", FakeClient, raising=False)
    monkeypatch.setattr(main, "DowMonitorService", FakeService, raising=False)

    asyncio.run(main._start_dow_monitor(app, tmp_path, provider, "http://engine"))

    assert events == [
        ("store", tmp_path),
        ("gateway", provider),
        ("client", "http://engine"),
        "start",
    ]
    assert app.state.dow_monitor_service.started == 1
    assert app.state.dow_monitor_service.daily_loader("01347.HK", NOW) == "daily"


def test_lifecycle_stops_monitor_before_closing_its_client() -> None:
    from app import main

    events: list[str] = []

    class FakeService:
        async def stop(self) -> None:
            events.append("stop")

    class FakeClient:
        def close(self) -> None:
            events.append("close")

    app = SimpleNamespace(
        state=SimpleNamespace(dow_monitor_service=FakeService(), dow_monitor_client=FakeClient())
    )

    asyncio.run(main._stop_dow_monitor(app))

    assert events == ["stop", "close"]
