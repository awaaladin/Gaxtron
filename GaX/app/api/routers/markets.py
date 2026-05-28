"""Public market data proxy — avoids browser CORS/rate-limit issues with CoinGecko."""
import logging
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/markets", tags=["markets"])

COINGECKO = "https://api.coingecko.com/api/v3"
COIN_IDS = "bitcoin,ethereum,solana,binancecoin,ripple,cardano,dogecoin,polkadot"

_cache: dict[str, tuple[float, Any]] = {}
_PRICES_TTL = 45
_CHART_TTL = 120

_FALLBACK_PRICES = {
    "bitcoin": {"usd": 64200, "usd_24h_change": 1.2},
    "ethereum": {"usd": 3420, "usd_24h_change": 0.8},
    "solana": {"usd": 148, "usd_24h_change": -0.5},
    "binancecoin": {"usd": 585, "usd_24h_change": 0.3},
    "ripple": {"usd": 0.52, "usd_24h_change": 1.1},
    "cardano": {"usd": 0.45, "usd_24h_change": -0.2},
    "dogecoin": {"usd": 0.12, "usd_24h_change": 2.1},
    "polkadot": {"usd": 7.2, "usd_24h_change": 0.4},
}


def _cached(key: str, ttl: float):
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < ttl:
        return entry[1]
    return None


def _set_cache(key: str, data: Any) -> None:
    _cache[key] = (time.time(), data)


def _fallback_chart(coin_id: str) -> list[list[float]]:
    base = _FALLBACK_PRICES.get(coin_id, {"usd": 100})["usd"]
    now = int(time.time() * 1000)
    step = 3600000
    return [[now - (23 - i) * step, base * (0.97 + 0.03 * (i / 23))] for i in range(24)]


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
                logger.warning("CoinGecko rate limited — using fallback prices")
                data = dict(_FALLBACK_PRICES)
            else:
                res.raise_for_status()
                data = res.json()
        _set_cache("prices", data)
        return data
    except Exception as exc:
        logger.warning("Market prices fetch failed: %s", exc)
        return dict(_FALLBACK_PRICES)


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
                prices = _fallback_chart(coin_id)
            else:
                res.raise_for_status()
                prices = res.json().get("prices") or _fallback_chart(coin_id)
        payload = {"prices": prices}
        _set_cache(key, payload)
        return payload
    except Exception as exc:
        logger.warning("Market chart fetch failed for %s: %s", coin_id, exc)
        return {"prices": _fallback_chart(coin_id), "fallback": True}
