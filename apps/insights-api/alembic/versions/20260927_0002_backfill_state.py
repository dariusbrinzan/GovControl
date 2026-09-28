"""Add resumable projection backfill state.

Revision ID: 20260927_0002
Revises: 20260926_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0002"
down_revision: str | None = "20260926_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backfill_states",
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("cursor", sa.BigInteger(), nullable=False),
        sa.Column("expected_count", sa.BigInteger(), nullable=False),
        sa.Column("imported_count", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_error", sa.String(length=500)),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("source"),
        schema="insights",
    )


def downgrade() -> None:
    op.drop_table("backfill_states", schema="insights")
