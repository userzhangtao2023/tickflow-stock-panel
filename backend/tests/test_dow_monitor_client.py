from __future__ import annotations

import json
from datetime import date, datetime

import httpx
import pytest

from app.services.dow_monitor_client import DowEngineUnavailable, LongbridgeDowClient


def _bars() -> list[dict[str, object]]:
    return [
        {
            "timestamp": "2026-07-17T15:00:00+08:00",
            "open": 138.2,
            "high": 139.0,
            "low": 137.1,
            "close": 138.0,
            "volume": 2_674_927,
        },
        {
            "timestamp": "2026-07-20T13:30:00+08:00",
            "open": 142.6,
            "high": 143.0,
            "low": 136.7,
            "close": 137.3,
            "volume": 6_541_068,
        },
        {
            "timestamp": "2026-07-23T10:30:00+08:00",
            "open": 148.9,
            "high": 152.5,
            "low": 148.7,
            "close": 149.8,
            "volume": 4_916_000,
        },
    ]


def _engine_response() -> dict[str, object]:
    return {
        "symbol": "01347.HK",
        "timeframe": "30m",
        "snapshot": {
            "symbol": "01347.HK",
            "timeframe": "30m",
            "bar_time": "2026-07-23T10:30:00+08:00",
            "bar_completion": "FORMING",
            "provisional": True,
            "phase": "无明确形态",
            "phase_code": "NONE",
            "candle_pattern": None,
            "line_id": "SUPPORT-MAIN-1",
            "line_role": "MAIN",
            "line_side": "SUPPORT",
            "line_anchor_times": [
                "2026-07-17T15:00:00+08:00",
                "2026-07-20T13:30:00+08:00",
            ],
            "line_value": 136.7,
            "price_to_line_pct": 9.58,
            "sequence_count": 0,
            "volume_ratio_20": 1.2,
            "volume_confirmation": "PENDING",
            "action": "观察",
            "action_code": "WATCH",
            "reason_codes": ["LINE_PRESENT"],
        },
        "bars": [{"index": index, **bar} for index, bar in enumerate(_bars())],
        "lines": [
            {
                "id": "SUPPORT-MAIN-1",
                "side": "SUPPORT",
                "role": "MAIN",
                "generation": 0,
                "anchorIndexes": [0, 1],
                "anchorTimes": [
                    "2026-07-17T15:00:00+08:00",
                    "2026-07-20T13:30:00+08:00",
                ],
                "anchorPrices": [137.1, 136.7],
                "createdIndex": 1,
                "invalidatedIndex": None,
                "controlsSignals": True,
            }
        ],
        "signals": [
            {
                "side": "BUY",
                "barIndex": 2,
                "barTime": "2026-07-23T10:30:00+08:00",
                "price": 149.8,
                "reason": "controlled_engine_signal",
                "confidence": "STRONG",
                "lineId": "SUPPORT-MAIN-1",
                "firstCrossIndex": 1,
                "firstCrossTime": "2026-07-20T13:30:00+08:00",
                "volumeRatio": 1.4,
                "pattern": "BIG_BULL",
                "evidence": [
                    {
                        "code": "CONTROLLED_BREAK",
                        "detector": "controlled_engine",
                        "side": "BUY",
                        "barIndex": 2,
                        "strength": "STRONG",
                        "structureId": "SUPPORT-MAIN-1",
                        "details": [{"name": "line_value", "value": 136.7}],
                    }
                ],
            }
        ],
        "longTerm": {
            "symbol": "01347.HK",
            "timeframe": "30m",
            "bar_time": "2026-07-23T10:30:00+08:00",
            "bar_completion": "FORMING",
            "provisional": True,
            "trend_direction": "DOWN",
            "trend_name": "长期下降趋势",
            "pattern_name": "长期下降趋势双突破",
            "operation": "观察",
            "signal_stage": "WARNING",
            "breakout_type": "DOUBLE_BREAKOUT",
            "line_id": "LONG-RESISTANCE-7",
            "line_side": "RESISTANCE",
            "line_status": "BREAK_PENDING",
            "first_anchor_time": "2026-07-17T15:00:00+08:00",
            "first_anchor_price": 143.0,
            "second_anchor_time": "2026-07-20T13:30:00+08:00",
            "second_anchor_price": 142.0,
            "line_value": 141.5,
            "key_level_type": "PRIMARY_LL",
            "key_level_time": "2026-07-17T14:30:00+08:00",
            "key_level_price": 136.3,
            "first_break_time": "2026-07-23T10:00:00+08:00",
            "recent_low_scale": "PRIMARY",
            "recent_low_label": "LL",
            "recent_low_time": "2026-07-17T14:30:00+08:00",
            "recent_low_price": 136.3,
            "recent_low_confirmed_time": "2026-07-17T15:00:00+08:00",
            "evidence_codes": ["LONG_LINE_BREAK", "KEY_LEVEL_BREAK"],
            "failure_reason": None,
        },
        "evaluatedAt": "2026-07-23T10:47:15+08:00",
    }


def _capture_transport(response: httpx.Response) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )

    return httpx.MockTransport(handler), requests


def test_client_sends_exact_external_bar_contract_and_preserves_engine_fields() -> None:
    transport, requests = _capture_transport(httpx.Response(200, json=_engine_response()))
    bars = _bars()
    as_of = datetime.fromisoformat("2026-07-23T10:47:15+08:00")

    result = LongbridgeDowClient(
        "http://127.0.0.1:19912/",
        transport=transport,
    ).evaluate("01347.HK", "30m", bars, "FORMING", as_of)

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url == httpx.URL("http://127.0.0.1:19912/api/dow-state/evaluate")
    assert json.loads(request.content) == {
        "symbol": "01347.HK",
        "timeframe": "30m",
        "completion": "FORMING",
        "asOf": "2026-07-23T10:47:15+08:00",
        "bars": bars,
    }
    assert result.snapshot.line_anchor_times == (
        "2026-07-17T15:00:00+08:00",
        "2026-07-20T13:30:00+08:00",
    )
    assert result.lines[0].role == "MAIN"
    assert result.lines[0].anchor_times == result.snapshot.line_anchor_times
    assert result.signals[0].evidence[0].structure_id == "SUPPORT-MAIN-1"
    assert result.signals[0].side == "BUY"
    assert result.long_term.pattern_name == "长期下降趋势双突破"
    assert result.long_term.first_anchor_time == datetime.fromisoformat("2026-07-17T15:00:00+08:00")
    assert result.long_term.evidence_codes == ("LONG_LINE_BREAK", "KEY_LEVEL_BREAK")
    assert isinstance(result.long_term.bar_time, (date, datetime))
    assert result.model_dump(mode="json", by_alias=True)["longTerm"]["bar_time"] == (
        "2026-07-23T10:30:00+08:00"
    )


def test_client_preserves_final_contract_without_reclassifying_bars() -> None:
    response = _engine_response()
    response["snapshot"] = {**response["snapshot"], "bar_completion": "FINAL", "provisional": False}
    transport, requests = _capture_transport(httpx.Response(200, json=response))
    bars = _bars()
    as_of = datetime.fromisoformat("2026-07-23T11:00:00+08:00")

    result = LongbridgeDowClient("http://engine", transport=transport).evaluate(
        "01347.HK", "30m", bars, "FINAL", as_of
    )

    assert json.loads(requests[0].content)["completion"] == "FINAL"
    assert json.loads(requests[0].content)["asOf"] == "2026-07-23T11:00:00+08:00"
    assert json.loads(requests[0].content)["bars"] == bars
    assert result.snapshot.bar_completion == "FINAL"
    assert result.snapshot.provisional is False


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(502, json={"detail": "upstream unavailable"}),
        httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"}),
        httpx.Response(200, json={"symbol": "01347.HK"}),
        httpx.Response(
            200,
            json={
                **_engine_response(),
                "longTerm": {**_engine_response()["longTerm"], "unexpected": True},
            },
        ),
    ],
)
def test_client_maps_http_json_and_schema_failures_to_engine_unavailable(
    response: httpx.Response,
) -> None:
    transport, _ = _capture_transport(response)
    client = LongbridgeDowClient("http://engine", transport=transport)

    with pytest.raises(DowEngineUnavailable):
        client.evaluate(
            "01347.HK",
            "30m",
            _bars(),
            "FORMING",
            datetime.fromisoformat("2026-07-23T10:47:15+08:00"),
        )


def test_client_maps_timeout_to_engine_unavailable_without_inferred_signal() -> None:
    def timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("engine timed out")

    client = LongbridgeDowClient("http://engine", transport=httpx.MockTransport(timeout))

    with pytest.raises(DowEngineUnavailable):
        client.evaluate(
            "01347.HK",
            "30m",
            _bars(),
            "FORMING",
            datetime.fromisoformat("2026-07-23T10:47:15+08:00"),
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provisional", "false"),
        ("bar_completion", "CLOSED"),
        ("signal_stage", "FORMAL"),
        ("trend_direction", "SIDEWAYS"),
        ("breakout_type", "BREAK"),
        ("operation", "立即买入"),
        ("bar_time", "not-a-time"),
        ("first_anchor_time", "not-a-time"),
        ("second_anchor_time", "not-a-time"),
        ("key_level_time", "not-a-time"),
        ("first_break_time", "not-a-time"),
        ("recent_low_time", "not-a-time"),
        ("recent_low_confirmed_time", "not-a-time"),
    ],
)
def test_client_rejects_malformed_authoritative_long_term_fields(
    field: str,
    value: object,
) -> None:
    response = _engine_response()
    response["longTerm"] = {**response["longTerm"], field: value}
    transport, _ = _capture_transport(httpx.Response(200, json=response))
    client = LongbridgeDowClient("http://engine", transport=transport)

    with pytest.raises(DowEngineUnavailable):
        client.evaluate(
            "01347.HK",
            "30m",
            _bars(),
            "FORMING",
            datetime.fromisoformat("2026-07-23T10:47:15+08:00"),
        )
