import logging
import os
import time
from collections import defaultdict

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None
_memory_windows: dict[str, list[float]] = defaultdict(list)


def get_redis() -> redis.Redis | None:
    global _redis
    try:
        if _redis is None:
            _redis = redis.from_url(settings.redis_url, decode_responses=True)
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
    """Fallback when Redis is unavailable (e.g. Vercel serverless without Redis)."""
    now = time.time()
    bucket = _memory_windows[key]
    _memory_windows[key] = [t for t in bucket if t > now - window]
    if len(_memory_windows[key]) >= limit:
        return False
    _memory_windows[key].append(now)
    return True


def check_rate_limit(identifier: str, *, limit: int | None = None, window: int | None = None) -> bool:
    """
    Return True if allowed.
    Uses Redis when available; falls back to in-memory on serverless (Vercel).
    """
    lim = limit or settings.api_rate_limit
    win = window or settings.api_rate_limit_window

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
        limit=settings.auth_rate_limit,
        window=settings.auth_rate_limit_window,
    )
