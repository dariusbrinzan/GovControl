"""Enforce role scope and system role uniqueness.

Revision ID: 20260921_0002
Revises: 20260921_0001
Create Date: 2026-09-21 00:01:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0002"
down_revision: str | None = "20260921_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_roles_scope_matches_tenant",
        "roles",
        "(scope = 'SYSTEM' AND tenant_id IS NULL) OR (scope = 'TENANT' AND tenant_id IS NOT NULL)",
    )
    op.create_index(
        "uq_roles_system_key",
        "roles",
        ["key"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_roles_system_key", table_name="roles")
    op.drop_constraint("ck_roles_scope_matches_tenant", "roles", type_="check")
