"""Proxy the materialized multi-timeframe Dow strategy from Longbridge."""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter, HTTPException, Query


router = APIRouter(prefix="/api/dow-strategy", tags=["dow-strategy"])


def _endpoint() -> str:
    return os.getenv("LONGBRIDGE_API_URL", "http://127.0.0.1:19912").rstrip("/")


def _payload(response: httpx.Response):
    try:
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Longbridge Dow strategy unavailable: {exc}") from exc


@router.get("/pool")
def pool(
    market: str = Query(pattern="^(cn|hk|us|all)$"),
    limit: int = Query(default=80, ge=1, le=500),
):
    response = httpx.get(
        f"{_endpoint()}/api/workbench",
        params={"market": market, "limit": limit, "strategy": "dow_trend"},
        timeout=30.0,
    )
    return _payload(response)


@router.get("/{symbol}")
def detail(symbol: str):
    return _payload(httpx.get(
        f"{_endpoint()}/api/dow-strategy/{symbol.strip().upper()}", timeout=30.0
    ))


@router.post("/backtest")
def backtest(payload: dict):
    return _payload(httpx.post(
        f"{_endpoint()}/api/dow-strategy/backtest", json=payload, timeout=180.0
    ))
