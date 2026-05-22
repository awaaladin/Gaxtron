"""Multi-chain columns

Revision ID: 002
Revises: 001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("chain", sa.String(10), server_default="ETH", nullable=False))
    op.create_index("ix_payments_chain", "payments", ["chain"])
    op.alter_column("payments", "wallet_address", type_=sa.String(128))
    op.alter_column("payments", "tx_hash", type_=sa.String(128))

    op.add_column("wallets", sa.Column("chain", sa.String(10), server_default="ETH", nullable=False))
    op.alter_column("wallets", "address", type_=sa.String(128))

    op.add_column("transactions", sa.Column("chain", sa.String(10), server_default="ETH", nullable=False))
    op.alter_column("transactions", "tx_hash", type_=sa.String(128))
    op.alter_column("transactions", "from_address", type_=sa.String(128))
    op.alter_column("transactions", "to_address", type_=sa.String(128))


def downgrade() -> None:
    op.drop_index("ix_payments_chain", "payments")
    op.drop_column("payments", "chain")
    op.drop_column("wallets", "chain")
    op.drop_column("transactions", "chain")
