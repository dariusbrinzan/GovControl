"""Track consumer liveness independently from projection changes.

Revision ID: 20260927_0003
Revises: 20260927_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0003"
down_revision: str | None = "20260927_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projection_checkpoints",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True)),
        schema="insights",
    )
    op.create_index(
        "ix_export_expires", "export_artifacts", ["expires_at"], schema="insights"
    )


def downgrade() -> None:
    op.drop_index("ix_export_expires", table_name="export_artifacts", schema="insights")
    op.drop_column("projection_checkpoints", "last_heartbeat_at", schema="insights")
