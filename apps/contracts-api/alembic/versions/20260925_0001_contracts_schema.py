"""Create the independently owned GovContracts schema.

Revision ID: 20260925_0001
Revises:
Create Date: 2026-09-25 00:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260925_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS contracts")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS contracts CASCADE")
