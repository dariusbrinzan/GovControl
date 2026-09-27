"""Create independently owned GovInsights schema.

Revision ID: 20260926_0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260926_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS insights")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "projection_resources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("module", sa.String(40), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("identifier", sa.String(255)),
        sa.Column("display_label", sa.String(500)),
        sa.Column("status", sa.String(80)),
        sa.Column("department_id", sa.UUID()),
        sa.Column("responsible_user_id", sa.UUID()),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("amount", sa.Numeric(20, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("source_version", sa.BigInteger(), nullable=False),
        sa.Column("source_event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "module", "resource_type", "source_id", name="uq_projection_source"
        ),
        schema="insights",
    )
    op.create_index(
        "ix_projection_tenant_module_status",
        "projection_resources",
        ["tenant_id", "module", "status"],
        schema="insights",
    )
    op.create_index(
        "ix_projection_tenant_due",
        "projection_resources",
        ["tenant_id", "due_at"],
        schema="insights",
    )
    op.create_index(
        "ix_projection_tenant_department",
        "projection_resources",
        ["tenant_id", "department_id"],
        schema="insights",
    )
    op.create_index(
        "ix_projection_tenant_responsible",
        "projection_resources",
        ["tenant_id", "responsible_user_id"],
        schema="insights",
    )
    op.execute(
        "CREATE INDEX ix_projection_search_trgm ON insights.projection_resources USING gin ((coalesce(identifier, '') || ' ' || coalesce(display_label, '')) gin_trgm_ops)"
    )

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column("stream_id", sa.String(64), nullable=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="insights",
    )
    op.create_index(
        "ix_insights_processed_events_tenant_id",
        "processed_events",
        ["tenant_id"],
        schema="insights",
    )
    op.create_table(
        "projection_checkpoints",
        sa.Column("consumer", sa.String(100), primary_key=True),
        sa.Column("last_stream_id", sa.String(64), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True)),
        sa.Column("last_processed_at", sa.DateTime(timezone=True)),
        sa.Column("processed_count", sa.BigInteger(), nullable=False),
        sa.Column("failed_count", sa.BigInteger(), nullable=False),
        sa.Column("projection_version", sa.BigInteger(), nullable=False),
        schema="insights",
    )
    op.create_table(
        "saved_reports",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False),
        sa.Column("columns", postgresql.JSONB(), nullable=False),
        sa.Column("sort", postgresql.JSONB(), nullable=False),
        sa.Column("shared_with_roles", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tenant_id", "owner_user_id", "name", name="uq_report_owner_name"),
        schema="insights",
    )
    op.create_index(
        "ix_report_tenant_owner", "saved_reports", ["tenant_id", "owner_user_id"], schema="insights"
    )
    op.create_table(
        "report_runs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("report_id", sa.UUID(), nullable=False),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("row_count", sa.Integer()),
        sa.Column("error_code", sa.String(100)),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        schema="insights",
    )
    op.create_index(
        "ix_report_run_tenant_requested",
        "report_runs",
        ["tenant_id", "requested_at"],
        schema="insights",
    )
    op.create_table(
        "export_artifacts",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("format", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("storage_key", sa.String(600), unique=True),
        sa.Column("content_type", sa.String(100)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("checksum_sha256", sa.String(64)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="insights",
    )
    op.create_index(
        "ix_export_tenant_owner",
        "export_artifacts",
        ["tenant_id", "owner_user_id"],
        schema="insights",
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("actor_user_id", sa.UUID()),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.UUID()),
        sa.Column("request_id", sa.UUID()),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema="insights",
    )
    op.create_index(
        "ix_insights_audit_tenant_created",
        "audit_events",
        ["tenant_id", "created_at"],
        schema="insights",
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        schema="insights",
    )
    op.create_index(
        "ix_insights_outbox_unpublished",
        "outbox_events",
        ["published_at", "created_at"],
        schema="insights",
    )


def downgrade() -> None:
    for table in (
        "outbox_events",
        "audit_events",
        "export_artifacts",
        "report_runs",
        "saved_reports",
        "projection_checkpoints",
        "processed_events",
        "projection_resources",
    ):
        op.drop_table(table, schema="insights")
