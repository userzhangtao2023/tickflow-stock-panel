from __future__ import annotations

from datetime import UTC, datetime
import importlib.util
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_dow_monitor_health.py"
SPEC = importlib.util.spec_from_file_location("check_dow_monitor_health", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
main = MODULE.main


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "request failed",
                request=httpx.Request("GET", "http://127.0.0.1:3018"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict:
        return self._payload


def _install_responses(
    monkeypatch,
    *,
    status: dict,
) -> None:
    def fake_get(url: str, **_kwargs) -> _Response:
        if url.endswith("/api/dow-monitor/status"):
            return _Response(status)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(httpx, "get", fake_get)


def test_health_probe_rejects_stopped_monitor(monkeypatch) -> None:
    _install_responses(
        monkeypatch,
        status={
            "running": False,
            "last_success_at": "2026-07-23T09:30:00+08:00",
        },
    )

    assert main(["--url", "http://127.0.0.1:3018", "--max-age-seconds", "120"]) == 1


def test_health_probe_rejects_stale_monitor_during_enabled_market_session(
    monkeypatch,
) -> None:
    _install_responses(
        monkeypatch,
        status={
            "running": True,
            "last_success_at": "2026-07-23T09:30:00+08:00",
            "enabled_markets": ["hk"],
            "open_enabled_markets": ["hk"],
        },
    )

    assert (
        main(
            ["--url", "http://127.0.0.1:3018", "--max-age-seconds", "120"],
            now_fn=lambda: datetime(2026, 7, 23, 2, 0, tzinfo=UTC),
        )
        == 1
    )


def test_health_probe_requires_only_running_outside_enabled_market_sessions(
    monkeypatch,
) -> None:
    _install_responses(
        monkeypatch,
        status={
            "running": True,
            "last_success_at": "2026-07-22T09:30:00+08:00",
            "enabled_markets": ["hk"],
            "open_enabled_markets": [],
        },
    )

    assert (
        main(
            ["--url", "http://127.0.0.1:3018", "--max-age-seconds", "120"],
            now_fn=lambda: datetime(2026, 7, 23, 9, 0, tzinfo=UTC),
        )
        == 0
    )


def test_health_probe_ignores_disabled_market_sessions(monkeypatch) -> None:
    _install_responses(
        monkeypatch,
        status={
            "running": True,
            "last_success_at": None,
            "enabled_markets": [],
            "open_enabled_markets": [],
        },
    )

    assert (
        main(
            ["--url", "http://127.0.0.1:3018", "--max-age-seconds", "120"],
            now_fn=lambda: datetime(2026, 7, 23, 14, 0, tzinfo=UTC),
        )
        == 0
    )


def test_health_probe_rejects_invalid_or_unreachable_responses(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("offline")),
    )
    assert main(["--url", "http://127.0.0.1:3018"]) == 1

    _install_responses(monkeypatch, status={"running": True})
    assert main(["--url", "http://127.0.0.1:3018"]) == 1
