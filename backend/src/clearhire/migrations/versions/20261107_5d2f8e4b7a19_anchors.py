"""anchors

Revision ID: 5d2f8e4b7a19
Revises: 3b7e2a91c0d4
Create Date: 2026-11-07 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5d2f8e4b7a19"
down_revision: str | None = "3b7e2a91c0d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anchors",
        sa.Column("period", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("period_seconds", sa.Integer(), nullable=False),
        sa.Column("root", sa.LargeBinary(length=32), nullable=False),
        sa.Column("head", sa.LargeBinary(length=32), nullable=False),
        sa.Column("first_id", sa.BigInteger(), nullable=False),
        sa.Column("last_id", sa.BigInteger(), nullable=False),
        sa.Column("entries", sa.Integer(), nullable=False),
        sa.Column("chain_id", sa.BigInteger(), nullable=False),
        sa.Column("contract", sa.String(length=42), nullable=False),
        sa.Column("tx_hash", sa.String(length=66), nullable=False),
        sa.Column("block", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("period"),
        sa.UniqueConstraint("last_id"),
    )


def downgrade() -> None:
    op.drop_table("anchors")
