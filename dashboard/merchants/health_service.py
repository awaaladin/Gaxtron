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


def check_blockchain_errors() -> dict[str, str | None]:
    """Call after check_blockchain()/check_all_chains() so each chain's is_connected()
    has run and recorded a fresh error — gives a specific reason instead of a bare bool."""
    try:
        processor = get_payment_processor()
        processor.chain_health()
        return processor.chain_errors()
    except Exception as exc:
        logger.exception("Blockchain error lookup failed")
        return {"_error": str(exc)}
