"""Public market data proxy — live CoinGecko only; no fabricated fallbacks."""
import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/markets", tags=["markets"])

COINGECKO = "https://api.coingecko.com/api/v3"
COIN_IDS = "bitcoin,ethereum,solana,binancecoin,ripple,cardano,dogecoin,polkadot"

_cache: dict[str, tuple[float, Any]] = {}
_PRICES_TTL = 45
_CHART_TTL = 120


def _cached(key: str, ttl: float):
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < ttl:
        return entry[1]
    return None


def _set_cache(key: str, data: Any) -> None:
    _cache[key] = (time.time(), data)


@router.get("/prices")
async def market_prices():
    cached = _cached("prices", _PRICES_TTL)
    if cached:
        return cached

    url = f"{COINGECKO}/simple/price?ids={COIN_IDS}&vs_currencies=usd&include_24hr_change=true"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            res = await client.get(url)
            if res.status_code == 429:
                logger.warning("CoinGecko rate limited")
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Market data temporarily unavailable (rate limit). Try again shortly."},
                )
            res.raise_for_status()
            data = res.json()
        if not data:
            raise ValueError("Empty price response")
        _set_cache("prices", data)
        return data
    except Exception as exc:
        logger.warning("Market prices fetch failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"detail": "Market data unavailable. Try again later."},
        )


@router.get("/chart/{coin_id}")
async def market_chart(coin_id: str):
    allowed = {c.strip() for c in COIN_IDS.split(",")}
    if coin_id not in allowed:
        raise HTTPException(status_code=404, detail="Unknown coin")

    key = f"chart:{coin_id}"
    cached = _cached(key, _CHART_TTL)
    if cached:
        return cached

    url = f"{COINGECKO}/coins/{coin_id}/market_chart?vs_currency=usd&days=1"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url)
            if res.status_code == 429:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Chart data temporarily unavailable (rate limit)."},
                )
            res.raise_for_status()
            prices = res.json().get("prices")
            if not prices:
                raise ValueError("Empty chart response")
        payload = {"prices": prices}
        _set_cache(key, payload)
        return payload
    except Exception as exc:
        logger.warning("Market chart fetch failed for %s: %s", coin_id, exc)
        return JSONResponse(
            status_code=503,
            content={"detail": "Chart data unavailable. Try again later."},
        )
