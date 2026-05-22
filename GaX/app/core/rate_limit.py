import logging
import time

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None


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


def check_rate_limit(identifier: str, *, limit: int | None = None, window: int | None = None) -> bool:
    """
    Return True if allowed. In production without Redis, deny (fail closed).
    In development without Redis, allow with warning.
    """
    r = get_redis()
    if r is None:
        if settings.is_production:
            return False
        logger.warning("Rate limit bypassed (dev, no Redis): %s", identifier)
        return True

    key = f"rate:{identifier}"
    return _sliding_window(
        r,
        key,
        limit or settings.api_rate_limit,
        window or settings.api_rate_limit_window,
    )


def check_auth_rate_limit(identifier: str) -> bool:
    return check_rate_limit(
        f"auth:{identifier}",
        limit=settings.auth_rate_limit,
        window=settings.auth_rate_limit_window,
    )
