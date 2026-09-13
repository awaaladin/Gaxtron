"""Ported from GaX/app/services/health_service.py — Django DB connection instead of
a raw SQLAlchemy engine."""
import logging

from django.db import connection

from .payment_processor import get_payment_processor
from .rate_limit import get_redis

logger = logging.getLogger(__name__)


def check_database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        logger.exception("Database health check failed")
        return False


def check_redis() -> bool:
    try:
        r = get_redis()
        return r is not None and bool(r.ping())
    except Exception:
        return False


def check_blockchain() -> bool:
    """At least one enabled chain RPC must be reachable."""
    try:
        health = get_payment_processor().chain_health()
        return any(health.values())
    except Exception:
        return False


def check_all_chains() -> dict[str, bool]:
    try:
        return get_payment_processor().chain_health()
    except Exception:
        return {}
