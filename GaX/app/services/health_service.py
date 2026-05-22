import logging



from sqlalchemy import text



from app.core.rate_limit import get_redis

from app.db.session import engine

from app.services.payment_processor import get_payment_processor



logger = logging.getLogger(__name__)





def check_database() -> bool:

    try:

        with engine.connect() as conn:

            conn.execute(text("SELECT 1"))

        return True

    except Exception:

        logger.exception("Database health check failed")

        return False





def check_redis() -> bool:

    try:

        r = get_redis()

        return r is not None and r.ping()

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


