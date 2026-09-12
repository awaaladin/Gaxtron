"""Redis-backed sliding-window rate limiter, with an in-memory fallback — ported
verbatim from GaX/app/core/rate_limit.py."""
import logging
import os
import time
from collections import defaultdict

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None
_memory_windows: dict[str, list[float]] = defaultdict(list)


def get_redis() -> redis.Redis | None:
    global _redis
    try:
        if _redis is None:
            _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        _redis.ping()
        return _redis
    except redis.RedisError:
        logger.warning("Redis unavailable for rate limiting")
        return None


def _sliding_window(r: redis.Redis, key: str, limit: int, window: int) -> bool:
    now = int(time.time())
    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, now - window)
    pipe.zadd(key, {f"{now}:{time.time_ns()}": now})
    pipe.zcard(key)
    pipe.expire(key, window)
    _, _, count, _ = pipe.execute()
    return count <= limit


def _memory_sliding_window(key: str, limit: int, window: int) -> bool:
    """Fallback when Redis is unavailable (e.g. serverless without Redis)."""
    now = time.time()
    bucket = _memory_windows[key]
    _memory_windows[key] = [t for t in bucket if t > now - window]
    if len(_memory_windows[key]) >= limit:
        return False
    _memory_windows[key].append(now)
    return True


def check_rate_limit(identifier: str, *, limit: int | None = None, window: int | None = None) -> bool:
    lim = limit or settings.API_RATE_LIMIT
    win = window or settings.API_RATE_LIMIT_WINDOW

    r = get_redis()
    if r is None:
        if os.getenv("VERCEL"):
            logger.debug("Rate limit (memory fallback on Vercel): %s", identifier)
        else:
            logger.warning("Rate limit memory fallback (no Redis): %s", identifier)
        return _memory_sliding_window(f"mem:{identifier}", lim, win)

    key = f"rate:{identifier}"
    return _sliding_window(r, key, lim, win)


def check_auth_rate_limit(identifier: str) -> bool:
    return check_rate_limit(
        f"auth:{identifier}",
        limit=settings.AUTH_RATE_LIMIT,
        window=settings.AUTH_RATE_LIMIT_WINDOW,
    )
