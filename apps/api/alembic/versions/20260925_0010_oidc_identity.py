"""Add issuer-qualified OIDC identity mapping.

Revision ID: 20260925_0010
Revises: 20260924_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260925_0010"
down_revision: str | None = "20260924_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("external_issuer", sa.String(length=2048), nullable=True))
    op.create_unique_constraint(
        "uq_users_external_identity",
        "users",
        ["external_issuer", "external_subject"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_external_identity", "users", type_="unique")
    op.drop_column("users", "external_issuer")
