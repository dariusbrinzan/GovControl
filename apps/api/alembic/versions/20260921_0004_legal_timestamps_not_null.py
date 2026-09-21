"""Enforce required GovLegal timestamps.

Revision ID: 20260921_0004
Revises: 20260921_0003
Create Date: 2026-09-21 00:03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260921_0004"
down_revision: str | None = "20260921_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table, column in (
        ("legal_cases", "created_at"),
        ("legal_cases", "updated_at"),
        ("court_decisions", "created_at"),
        ("legal_obligations", "created_at"),
        ("legal_obligations", "updated_at"),
        ("obligation_status_history", "changed_at"),
    ):
        op.alter_column(table, column, existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    for table, column in (
        ("legal_cases", "created_at"),
        ("legal_cases", "updated_at"),
        ("court_decisions", "created_at"),
        ("legal_obligations", "created_at"),
        ("legal_obligations", "updated_at"),
        ("obligation_status_history", "changed_at"),
    ):
        op.alter_column(table, column, existing_type=sa.DateTime(timezone=True), nullable=True)
