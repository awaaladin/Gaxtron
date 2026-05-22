import json
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

QUEUE_PAYMENT_EVENTS = "gaxtron:payment_events"
QUEUE_WEBHOOK_DELIVERY = "gaxtron:webhook_delivery"
PROCESSED_EVENTS = "gaxtron:processed_events"


def get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def enqueue_payment_check(payment_id: int) -> None:
    try:
        r = get_redis()
        r.lpush(QUEUE_PAYMENT_EVENTS, json.dumps({"payment_id": payment_id}))
        logger.debug("Enqueued payment check %s", payment_id)
    except Exception:
        logger.warning("Redis unavailable — worker will poll payment %s", payment_id)


def enqueue_webhook(webhook_log_id: int) -> None:
    try:
        r = get_redis()
        r.lpush(QUEUE_WEBHOOK_DELIVERY, json.dumps({"webhook_log_id": webhook_log_id}))
        logger.debug("Enqueued webhook %s", webhook_log_id)
    except Exception:
        logger.warning("Redis unavailable — webhook %s not queued", webhook_log_id)


def is_event_processed(event_id: str) -> bool:
    try:
        return get_redis().sismember(PROCESSED_EVENTS, event_id)
    except Exception:
        return False


def mark_event_processed(event_id: str) -> None:
    try:
        get_redis().sadd(PROCESSED_EVENTS, event_id)
    except Exception:
        logger.debug("Redis unavailable — idempotency relies on DB tx_hash only")
