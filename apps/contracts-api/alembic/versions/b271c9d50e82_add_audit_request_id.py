"""add audit request correlation id

Revision ID: b271c9d50e82
Revises: a180faa2a5ec
Create Date: 2026-09-25 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b271c9d50e82"
down_revision: str | None = "a180faa2a5ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column("request_id", sa.UUID(), nullable=True),
        schema="contracts",
    )
    op.create_index(
        op.f("ix_contracts_audit_events_request_id"),
        "audit_events",
        ["request_id"],
        unique=False,
        schema="contracts",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_contracts_audit_events_request_id"),
        table_name="audit_events",
        schema="contracts",
    )
    op.drop_column("audit_events", "request_id", schema="contracts")
