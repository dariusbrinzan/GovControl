"""Add indexes supporting tenant-scoped analytics queries.

Revision ID: 20260924_0009
Revises: 20260922_0008
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260924_0009"
down_revision: str | None = "20260922_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_legal_obligations_tenant_created_at",
        "legal_obligations",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_legal_obligations_tenant_status_due_date",
        "legal_obligations",
        ["tenant_id", "status", "due_date"],
    )
    op.create_index(
        "ix_enforcement_proceedings_tenant_status",
        "enforcement_proceedings",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_penalty_rules_tenant_start_date",
        "penalty_rules",
        ["tenant_id", "start_date"],
    )
    op.create_index(
        "ix_obligation_status_history_tenant_changed_at",
        "obligation_status_history",
        ["tenant_id", "changed_at"],
    )
    op.create_index(
        "ix_audit_events_tenant_created_at",
        "audit_events",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_tenant_created_at", table_name="audit_events")
    op.drop_index(
        "ix_obligation_status_history_tenant_changed_at",
        table_name="obligation_status_history",
    )
    op.drop_index("ix_penalty_rules_tenant_start_date", table_name="penalty_rules")
    op.drop_index(
        "ix_enforcement_proceedings_tenant_status",
        table_name="enforcement_proceedings",
    )
    op.drop_index(
        "ix_legal_obligations_tenant_status_due_date",
        table_name="legal_obligations",
    )
    op.drop_index(
        "ix_legal_obligations_tenant_created_at",
        table_name="legal_obligations",
    )
