"""Lightweight schema patches (no Alembic) — aligns old DBs with current models."""
import logging
import uuid

from sqlalchemy import inspect, text

from app.db.session import engine

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    """Run on a single connection to avoid SQLite pool deadlocks at startup."""
    dialect = engine.dialect.name
    is_pg = dialect == "postgresql"

    with engine.begin() as conn:
        insp = inspect(conn)
        tables = set(insp.get_table_names())

        if "payments" in tables:
            payment_cols = {c["name"] for c in insp.get_columns("payments")}
            if "chain" not in payment_cols:
                if is_pg:
                    conn.execute(
                        text(
                            "ALTER TABLE payments ADD COLUMN IF NOT EXISTS "
                            "chain VARCHAR(10) NOT NULL DEFAULT 'ETH'"
                        )
                    )
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_payments_chain ON payments (chain)"))
                else:
                    conn.execute(
                        text("ALTER TABLE payments ADD COLUMN chain VARCHAR(10) NOT NULL DEFAULT 'ETH'")
                    )
                logger.info("Added payments.chain")
            if "confirmations" not in payment_cols:
                if is_pg:
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
                logger.info("Added payments.confirmations")

            payment_cols = {c["name"] for c in insp.get_columns("payments")}
            if "public_token" not in payment_cols:
                if is_pg:
                    conn.execute(
                        text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS public_token VARCHAR(72)")
                    )
                else:
                    conn.execute(text("ALTER TABLE payments ADD COLUMN public_token VARCHAR(72)"))
                logger.info("Added payments.public_token")
                rows = conn.execute(text("SELECT id FROM payments WHERE public_token IS NULL")).fetchall()
                for (pid,) in rows:
                    token = f"pay_{uuid.uuid4().hex}"
                    conn.execute(
                        text("UPDATE payments SET public_token = :t WHERE id = :id"),
                        {"t": token, "id": pid},
                    )
                if is_pg:
                    conn.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS ix_payments_public_token "
                            "ON payments (public_token)"
                        )
                    )
                logger.info("Backfilled public_token for %s payment(s)", len(rows))

        if "wallets" in tables:
            wallet_cols = {c["name"] for c in insp.get_columns("wallets")}
            if "chain" not in wallet_cols:
                if is_pg:
                    conn.execute(
                        text(
                            "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS "
                            "chain VARCHAR(10) NOT NULL DEFAULT 'ETH'"
                        )
                    )
                else:
                    conn.execute(
                        text("ALTER TABLE wallets ADD COLUMN chain VARCHAR(10) NOT NULL DEFAULT 'ETH'")
                    )
                logger.info("Added wallets.chain")

        if "transactions" in tables:
            tx_cols = {c["name"] for c in insp.get_columns("transactions")}
            if "chain" not in tx_cols:
                if is_pg:
                    conn.execute(
                        text(
                            "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS "
                            "chain VARCHAR(10) NOT NULL DEFAULT 'ETH'"
                        )
                    )
                else:
                    conn.execute(
                        text(
                            "ALTER TABLE transactions ADD COLUMN chain VARCHAR(10) NOT NULL DEFAULT 'ETH'"
                        )
                    )
                logger.info("Added transactions.chain")

        if "users" in tables:
            user_cols = {c["name"] for c in insp.get_columns("users")}
            if "wallet_address" not in user_cols:
                if is_pg:
                    conn.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                            "wallet_address VARCHAR(42)"
                        )
                    )
                    conn.execute(
                        text(
                            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_wallet_address "
                            "ON users (wallet_address)"
                        )
                    )
                else:
                    conn.execute(text("ALTER TABLE users ADD COLUMN wallet_address VARCHAR(42)"))
                logger.info("Added users.wallet_address")


if __name__ == "__main__":
    run_migrations()
    print("Migrations applied")
