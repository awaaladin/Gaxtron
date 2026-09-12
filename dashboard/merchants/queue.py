"""Ported verbatim from GaX/app/workers/queue.py."""
import json
import logging

import redis
from django.conf import settings

logger = logging.getLogger(__name__)

QUEUE_PAYMENT_EVENTS = "gaxtron:payment_events"
QUEUE_WEBHOOK_DELIVERY = "gaxtron:webhook_delivery"
PROCESSED_EVENTS = "gaxtron:processed_events"


def get_redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


def enqueue_payment_check(payment_id: int) -> None:
    try:
        get_redis().lpush(QUEUE_PAYMENT_EVENTS, json.dumps({"payment_id": payment_id}))
    except Exception:
        logger.warning("Redis unavailable — worker will poll payment %s", payment_id)


def enqueue_webhook(webhook_log_id: int) -> None:
    try:
        get_redis().lpush(QUEUE_WEBHOOK_DELIVERY, json.dumps({"webhook_log_id": webhook_log_id}))
    except Exception:
        logger.warning("Redis unavailable — webhook %s not queued", webhook_log_id)


def is_event_processed(event_id: str) -> bool:
    try:
        return bool(get_redis().sismember(PROCESSED_EVENTS, event_id))
    except Exception:
        return False


def mark_event_processed(event_id: str) -> None:
    try:
        get_redis().sadd(PROCESSED_EVENTS, event_id)
    except Exception:
        logger.debug("Redis unavailable — idempotency relies on DB tx_hash only")
