from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from json import JSONDecodeError
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class DowEngineUnavailable(RuntimeError):  # noqa: N818 - public engine contract name
    """The authoritative Longbridge Dow engine could not provide a usable result."""


class _EngineModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DowBar(_EngineModel):
    index: int
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class DowLine(_EngineModel):
    id: str
    side: str
    role: str
    generation: int
    anchor_indexes: tuple[int, int] = Field(alias="anchorIndexes")
    anchor_times: tuple[str, str] = Field(alias="anchorTimes")
    anchor_prices: tuple[float, float] = Field(alias="anchorPrices")
    created_index: int = Field(alias="createdIndex")
    invalidated_index: int | None = Field(alias="invalidatedIndex")
    controls_signals: bool = Field(alias="controlsSignals")


class DowSignalDetail(_EngineModel):
    name: str
    value: Any


class DowSignalEvidence(_EngineModel):
    code: str
    detector: str
    side: str
    bar_index: int = Field(alias="barIndex")
    strength: str
    structure_id: str | None = Field(alias="structureId")
    details: tuple[DowSignalDetail, ...]


class DowSignal(_EngineModel):
    side: str
    bar_index: int = Field(alias="barIndex")
    bar_time: str = Field(alias="barTime")
    price: float
    reason: str
    confidence: str
    line_id: str | None = Field(alias="lineId")
    first_cross_index: int | None = Field(alias="firstCrossIndex")
    first_cross_time: str | None = Field(alias="firstCrossTime")
    volume_ratio: float | None = Field(alias="volumeRatio")
    pattern: str | None
    evidence: tuple[DowSignalEvidence, ...]


class DowSnapshot(_EngineModel):
    symbol: str
    timeframe: str
    bar_time: str
    bar_completion: str
    provisional: bool
    phase: str
    phase_code: str
    candle_pattern: str | None
    line_id: str | None
    line_role: str | None
    line_side: str | None
    line_anchor_times: tuple[str, ...]
    line_value: float | None
    price_to_line_pct: float | None
    sequence_count: int
    volume_ratio_20: float | None
    volume_confirmation: str
    action: str
    action_code: str
    reason_codes: tuple[str, ...]


class DowEngineResult(_EngineModel):
    symbol: str
    timeframe: str
    snapshot: DowSnapshot
    bars: tuple[DowBar, ...]
    lines: tuple[DowLine, ...]
    signals: tuple[DowSignal, ...]
    evaluated_at: datetime = Field(alias="evaluatedAt")


class LongbridgeDowClient:
    def __init__(
        self,
        endpoint: str,
        timeout_s: float = 20.0,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=endpoint.rstrip("/") + "/",
            timeout=timeout_s,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> LongbridgeDowClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def evaluate(
        self,
        symbol: str,
        timeframe: str,
        bars: Sequence[Mapping[str, object]],
        completion: str,
        as_of: datetime,
    ) -> DowEngineResult:
        payload = {
            "symbol": symbol,
            "timeframe": timeframe,
            "completion": completion,
            "asOf": as_of.isoformat(),
            "bars": bars,
        }
        try:
            response = self._client.post("/api/dow-state/evaluate", json=payload)
            response.raise_for_status()
            return DowEngineResult.model_validate(response.json())
        except (httpx.HTTPError, JSONDecodeError, ValidationError) as exc:
            raise DowEngineUnavailable(str(exc)) from exc
