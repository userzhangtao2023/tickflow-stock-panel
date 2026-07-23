#!/usr/bin/env python
"""Exit non-zero when the TickFlow Dow monitor is stopped or stale."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
import sys

import httpx


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="TickFlow base URL")
    parser.add_argument("--max-age-seconds", type=float, default=120.0)
    return parser


def _aware_datetime(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("last_success_at must include a timezone")
    return parsed


def main(
    argv: Sequence[str] | None = None,
    *,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int:
    args = _parser().parse_args(argv)
    if args.max_age_seconds <= 0:
        print("--max-age-seconds must be greater than zero", file=sys.stderr)
        return 1

    try:
        response = httpx.get(
            f"{args.url.rstrip('/')}/api/dow-monitor/status",
            timeout=5.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("status response must be an object")
        if payload.get("running") is not True:
            raise ValueError("monitor is not running")

        open_markets = payload["open_enabled_markets"]
        if not isinstance(open_markets, list) or any(
            market not in {"cn", "hk", "us"} for market in open_markets
        ):
            raise ValueError("open_enabled_markets is invalid")
        if open_markets:
            last_success = _aware_datetime(payload.get("last_success_at"))
            now = now_fn()
            if now.tzinfo is None or now.utcoffset() is None:
                raise ValueError("now_fn must return a timezone-aware datetime")
            age_seconds = (
                now.astimezone(timezone.utc) - last_success.astimezone(timezone.utc)
            ).total_seconds()
            if age_seconds > args.max_age_seconds:
                raise ValueError(
                    f"last successful cycle is stale ({age_seconds:.1f}s > "
                    f"{args.max_age_seconds:.1f}s)"
                )
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        print(f"Dow monitor unhealthy: {exc}", file=sys.stderr)
        return 1

    print("Dow monitor healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
