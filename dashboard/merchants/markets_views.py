"""Public market data proxy — ported from GaX/app/api/routers/markets.py (sync httpx instead
of async, same as the rest of this port — no event loop backing plain Django views)."""
import logging
import time
from typing import Any

import httpx
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

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


class MarketPricesView(APIView):
    def get(self, request):
        cached = _cached("prices", _PRICES_TTL)
        if cached:
            return Response(cached)

        url = f"{COINGECKO}/simple/price?ids={COIN_IDS}&vs_currencies=usd&include_24hr_change=true"
        try:
            with httpx.Client(timeout=12.0) as client:
                res = client.get(url)
                if res.status_code == 429:
                    logger.warning("CoinGecko rate limited")
                    return Response({"detail": "Market data temporarily unavailable (rate limit). Try again shortly."}, status=503)
                res.raise_for_status()
                data = res.json()
            if not data:
                raise ValueError("Empty price response")
            _set_cache("prices", data)
            return Response(data)
        except Exception as exc:
            logger.warning("Market prices fetch failed: %s", exc)
            return Response({"detail": "Market data unavailable. Try again later."}, status=503)


class MarketChartView(APIView):
    def get(self, request, coin_id: str):
        allowed = {c.strip() for c in COIN_IDS.split(",")}
        if coin_id not in allowed:
            return Response({"detail": "Unknown coin"}, status=404)

        key = f"chart:{coin_id}"
        cached = _cached(key, _CHART_TTL)
        if cached:
            return Response(cached)

        url = f"{COINGECKO}/coins/{coin_id}/market_chart?vs_currency=usd&days=1"
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(url)
                if res.status_code == 429:
                    return Response({"detail": "Chart data temporarily unavailable (rate limit)."}, status=503)
                res.raise_for_status()
                prices = res.json().get("prices")
                if not prices:
                    raise ValueError("Empty chart response")
            payload = {"prices": prices}
            _set_cache(key, payload)
            return Response(payload)
        except Exception as exc:
            logger.warning("Market chart fetch failed for %s: %s", coin_id, exc)
            return Response({"detail": "Chart data unavailable. Try again later."}, status=503)
