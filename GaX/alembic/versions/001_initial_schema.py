"""Initial gaxtron schema

Revision ID: 001
Revises:
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("username", sa.String(100), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("is_superadmin", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(12), nullable=False),
        sa.Column("name", sa.String(100)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("last_used_at", sa.DateTime()),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("wallet_address", sa.String(64), nullable=False),
        sa.Column("callback_url", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(64), unique=True),
        sa.Column("tx_hash", sa.String(66)),
        sa.Column("event_id", sa.String(64), unique=True),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("confirmed_at", sa.DateTime()),
        sa.Column("expires_at", sa.DateTime()),
    )
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_wallet_address", "payments", ["wallet_address"])

    op.create_table(
        "wallets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id")),
        sa.Column("address", sa.String(64), nullable=False, unique=True),
        sa.Column("encrypted_private_key", sa.Text(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("balance", sa.Numeric(36, 18), server_default="0"),
        sa.Column("created_at", sa.DateTime()),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id")),
        sa.Column("tx_hash", sa.String(66), nullable=False, unique=True),
        sa.Column("amount", sa.Numeric(36, 18), nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("from_address", sa.String(64), nullable=False),
        sa.Column("to_address", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20)),
        sa.Column("confirmations", sa.Integer(), server_default="0"),
        sa.Column("block_number", sa.Integer()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_transactions_tx_hash", "transactions", ["tx_hash"], unique=True)

    op.create_table(
        "webhook_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payments.id"), nullable=False),
        sa.Column("event_id", sa.String(64), nullable=False, unique=True),
        sa.Column("callback_url", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20)),
        sa.Column("response_code", sa.Integer()),
        sa.Column("response_body", sa.Text()),
        sa.Column("attempts", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("delivered_at", sa.DateTime()),
    )


def downgrade() -> None:
    op.drop_table("webhook_logs")
    op.drop_table("transactions")
    op.drop_table("wallets")
    op.drop_table("payments")
    op.drop_table("api_keys")
    op.drop_table("users")
