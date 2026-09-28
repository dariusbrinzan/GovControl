"""Add explicit currency to penalty rules.

Revision ID: 20260927_0015
Revises: 20260927_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0015"
down_revision: str | None = "20260927_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "penalty_rules",
        sa.Column("currency", sa.String(length=3), server_default="RON", nullable=False),
    )
    op.create_check_constraint(
        "ck_penalty_rules_currency_iso",
        "penalty_rules",
        "currency ~ '^[A-Z]{3}$'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_penalty_rules_currency_iso", "penalty_rules", type_="check")
    op.drop_column("penalty_rules", "currency")
