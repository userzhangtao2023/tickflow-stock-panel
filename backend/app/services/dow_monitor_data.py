from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

import polars as pl

from app.market_rules import market_for_symbol

QUOTE_MAX_AGE = timedelta(seconds=90)
MINUTE_MAX_AGE = timedelta(seconds=120)

FreshnessState = Literal["LIVE", "STALE_DATA"]
FreshnessReason = Literal["QUOTE_TOO_OLD", "MINUTE_TOO_OLD", "SESSION_GAP"]


@dataclass(frozen=True)
class MarketSessionPolicy:
    timezone: str
    sessions: tuple[tuple[time, time], ...]


@dataclass(frozen=True)
class SymbolFreshness:
    state: FreshnessState
    reason: FreshnessReason | None


@dataclass(frozen=True)
class WebStockBatch:
    quotes: list[dict]
    minute_rows: pl.DataFrame
    source_timestamp: datetime | None
    freshness_by_symbol: dict[str, SymbolFreshness]
    gap_details: dict[str, list[datetime]]


class StrictWebStockProvider(Protocol):
    def get_realtime_strict(self, symbols: list[str]) -> list[dict]: ...

    def get_minute_strict(
        self,
        symbols: list[str],
        start_time: datetime,
        end_time: datetime,
    ) -> pl.DataFrame: ...


_SESSION_POLICIES = {
    "cn": MarketSessionPolicy(
        timezone="Asia/Shanghai",
        sessions=((time(9, 30), time(11, 30)), (time(13), time(15))),
    ),
    "hk": MarketSessionPolicy(
        timezone="Asia/Hong_Kong",
        sessions=((time(9, 30), time(12)), (time(13), time(16))),
    ),
    "us": MarketSessionPolicy(
        timezone="America/New_York",
        sessions=((time(9, 30), time(16)),),
    ),
}


def market_session_policy(symbol: str) -> MarketSessionPolicy:
    return _SESSION_POLICIES[market_for_symbol(symbol)]


def minute_range(local_date: date, start: time, end: time) -> Iterator[datetime]:
    cursor = datetime.combine(local_date, start)
    stop = datetime.combine(local_date, end)
    while cursor < stop:
        yield cursor
        cursor += timedelta(minutes=1)


def expected_minutes(symbol: str, local_date: date) -> set[datetime]:
    if local_date.weekday() >= 5:
        return set()
    policy = market_session_policy(symbol)
    return {
        cursor
        for session_start, session_end in policy.sessions
        for cursor in minute_range(local_date, session_start, session_end)
    }


def _as_utc(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC)
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _as_market_local(value: datetime, zone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(zone).replace(tzinfo=None)


def _minute_local(value: object, zone: ZoneInfo) -> datetime | None:
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(zone).replace(tzinfo=None)


def _is_regular_session(now_local: datetime, policy: MarketSessionPolicy) -> bool:
    if now_local.weekday() >= 5:
        return False
    local_time = now_local.time()
    return any(start <= local_time < end for start, end in policy.sessions)


def _expected_between(
    symbol: str,
    start: datetime,
    end: datetime,
    observed_dates: set[date],
) -> set[datetime]:
    if end < start:
        return set()
    return {
        value
        for observed_date in observed_dates
        for value in expected_minutes(symbol, observed_date)
        if start <= value <= end
    }


class WebStockMonitorGateway:
    def __init__(
        self,
        provider: StrictWebStockProvider,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._provider = provider
        self._now_fn = now_fn

    def fetch(
        self,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> WebStockBatch:
        normalized_symbols = list(
            dict.fromkeys(
                normalized for symbol in symbols if (normalized := str(symbol).strip().upper())
            )
        )
        if not normalized_symbols:
            return WebStockBatch(
                quotes=[],
                minute_rows=pl.DataFrame(),
                source_timestamp=None,
                freshness_by_symbol={},
                gap_details={},
            )

        now = self._now_fn()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now_fn must return a timezone-aware datetime")

        quotes = self._provider.get_realtime_strict(normalized_symbols)
        minute_rows = self._provider.get_minute_strict(normalized_symbols, start, end)
        now_utc = now.astimezone(UTC)
        rows = minute_rows.to_dicts() if not minute_rows.is_empty() else []
        quote_by_symbol = self._latest_quotes(quotes)

        source_times = [
            timestamp for row in quotes if (timestamp := _as_utc(row.get("timestamp"))) is not None
        ]
        freshness_by_symbol: dict[str, SymbolFreshness] = {}
        gap_details: dict[str, list[datetime]] = {}

        for symbol in normalized_symbols:
            policy = market_session_policy(symbol)
            zone = ZoneInfo(policy.timezone)
            now_local = _as_market_local(now, zone)
            start_local = _as_market_local(start, zone)
            end_local = min(_as_market_local(end, zone), now_local)

            observed = {
                local_time
                for row in rows
                if str(row.get("symbol") or "").upper() == symbol
                and (local_time := _minute_local(row.get("datetime"), zone)) is not None
                and start_local <= local_time <= end_local
                and local_time in expected_minutes(symbol, local_time.date())
            }
            expected = _expected_between(
                symbol,
                start_local,
                end_local,
                {local_time.date() for local_time in observed},
            )
            received = observed & expected
            latest_minute = max(received, default=None)
            gaps = (
                sorted(
                    value for value in expected if value <= latest_minute and value not in received
                )
                if latest_minute is not None
                else []
            )
            gap_details[symbol] = gaps

            if latest_minute is not None:
                source_times.append(latest_minute.replace(tzinfo=zone).astimezone(UTC))

            quote_time = _as_utc((quote_by_symbol.get(symbol) or {}).get("timestamp"))
            regular_session = _is_regular_session(now_local, policy)
            reason: FreshnessReason | None = None
            if regular_session and (quote_time is None or now_utc - quote_time > QUOTE_MAX_AGE):
                reason = "QUOTE_TOO_OLD"
            elif regular_session and (
                latest_minute is None
                or now_utc - latest_minute.replace(tzinfo=zone).astimezone(UTC) > MINUTE_MAX_AGE
            ):
                reason = "MINUTE_TOO_OLD"
            elif gaps:
                reason = "SESSION_GAP"

            freshness_by_symbol[symbol] = SymbolFreshness(
                state="STALE_DATA" if reason is not None else "LIVE",
                reason=reason,
            )

        return WebStockBatch(
            quotes=quotes,
            minute_rows=minute_rows,
            source_timestamp=max(source_times, default=None),
            freshness_by_symbol=freshness_by_symbol,
            gap_details=gap_details,
        )

    @staticmethod
    def _latest_quotes(quotes: list[dict]) -> dict[str, dict]:
        latest: dict[str, dict] = {}
        for row in quotes:
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            timestamp = _as_utc(row.get("timestamp"))
            previous = latest.get(symbol)
            previous_timestamp = _as_utc(previous.get("timestamp")) if previous else None
            if previous is None or (
                timestamp is not None
                and (previous_timestamp is None or timestamp >= previous_timestamp)
            ):
                latest[symbol] = row
        return latest
