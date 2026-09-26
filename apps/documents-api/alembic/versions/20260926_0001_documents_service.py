"""Create the independent GovDocuments schema.

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
    op.execute("CREATE SCHEMA IF NOT EXISTS documents")
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("classification", sa.String(50), nullable=False),
        sa.Column("retention_until", sa.Date()),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="documents",
    )
    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"], schema="documents")
    op.create_index("ix_documents_deleted_at", "documents", ["deleted_at"], schema="documents")
    op.create_index("ix_documents_tenant_state", "documents", ["tenant_id", "state"], schema="documents")
    op.create_index("ix_documents_tenant_created", "documents", ["tenant_id", "created_at"], schema="documents")
    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("safe_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(255), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("rejection_reason", sa.String(500)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_versions_document_number"),
        sa.UniqueConstraint("storage_key", name="uq_document_versions_storage_key"),
        schema="documents",
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"], schema="documents")
    op.create_index("ix_document_versions_tenant_id", "document_versions", ["tenant_id"], schema="documents")
    op.create_index("ix_document_versions_tenant_checksum", "document_versions", ["tenant_id", "checksum_sha256"], schema="documents")
    op.create_table(
        "document_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("document_id", "resource_type", "resource_id", name="uq_document_links_resource"),
        schema="documents",
    )
    op.create_index("ix_document_links_document_id", "document_links", ["document_id"], schema="documents")
    op.create_index("ix_document_links_tenant_resource", "document_links", ["tenant_id", "resource_type", "resource_id"], schema="documents")
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True)),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="documents",
    )
    op.create_index("ix_document_audit_tenant_created", "audit_events", ["tenant_id", "created_at"], schema="documents")
    op.create_index("ix_document_audit_tenant_id", "audit_events", ["tenant_id"], schema="documents")
    op.create_index("ix_document_audit_document_id", "audit_events", ["document_id"], schema="documents")
    op.create_index("ix_document_audit_request_id", "audit_events", ["request_id"], schema="documents")
    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(200), nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        schema="documents",
    )
    op.create_index("ix_document_outbox_unpublished", "outbox_events", ["published_at", "created_at"], schema="documents")
    op.create_index("ix_document_outbox_tenant_id", "outbox_events", ["tenant_id"], schema="documents")
    op.create_index("ix_document_outbox_aggregate_id", "outbox_events", ["aggregate_id"], schema="documents")
    op.create_table(
        "idempotency_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "key", name="uq_document_idempotency_tenant_key"),
        schema="documents",
    )
    op.create_index("ix_document_idempotency_tenant_id", "idempotency_records", ["tenant_id"], schema="documents")


def downgrade() -> None:
    op.drop_table("idempotency_records", schema="documents")
    op.drop_table("outbox_events", schema="documents")
    op.drop_table("audit_events", schema="documents")
    op.drop_table("document_links", schema="documents")
    op.drop_table("document_versions", schema="documents")
    op.drop_table("documents", schema="documents")
    op.execute("DROP SCHEMA IF EXISTS documents")
