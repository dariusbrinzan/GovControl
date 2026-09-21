"""Create document metadata.

Revision ID: 20260921_0006
Revises: 20260921_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260921_0006"
down_revision: str | None = "20260921_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("documents", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False), sa.Column("entity_type", sa.String(100), nullable=False), sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("category", sa.String(100), nullable=False), sa.Column("original_filename", sa.String(255), nullable=False), sa.Column("content_type", sa.String(255), nullable=False), sa.Column("size_bytes", sa.Integer(), nullable=False), sa.Column("checksum_sha256", sa.String(64), nullable=False), sa.Column("storage_key", sa.String(512), nullable=False, unique=True), sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    for column in ("tenant_id", "entity_type", "entity_id"):
        op.create_index(f"ix_documents_{column}", "documents", [column])


def downgrade() -> None:
    op.drop_table("documents")
