"""Add Platform/GovLegal transactional outbox.

Revision ID: 20260926_0013
Revises: 20260926_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260926_0013"
down_revision: str | None = "20260926_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integration_outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_platform_outbox_unpublished",
        "integration_outbox_events",
        ["published_at", "created_at"],
    )
    op.create_index(
        "ix_integration_outbox_events_tenant_id",
        "integration_outbox_events",
        ["tenant_id"],
    )
    op.create_index(
        "ix_integration_outbox_events_aggregate_id",
        "integration_outbox_events",
        ["aggregate_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_integration_outbox_events_aggregate_id", table_name="integration_outbox_events")
    op.drop_index("ix_integration_outbox_events_tenant_id", table_name="integration_outbox_events")
    op.drop_index("ix_platform_outbox_unpublished", table_name="integration_outbox_events")
    op.drop_table("integration_outbox_events")
