"""Lightweight schema patches (no Alembic)."""
import logging

from sqlalchemy import inspect, text

from app.db.session import engine

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    insp = inspect(engine)
    if "payments" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("payments")}
    with engine.begin() as conn:
        if "confirmations" not in cols:
            dialect = engine.dialect.name
            if dialect == "postgresql":
                conn.execute(
                    text(
                        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS "
                        "confirmations INTEGER NOT NULL DEFAULT 0"
                    )
                )
            else:
                conn.execute(
                    text("ALTER TABLE payments ADD COLUMN confirmations INTEGER NOT NULL DEFAULT 0")
                )
            logger.info("Added payments.confirmations column")


if __name__ == "__main__":
    run_migrations()
    print("Migrations applied")
