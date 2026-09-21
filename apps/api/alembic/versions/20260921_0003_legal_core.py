"""Create GovLegal core tables.

Revision ID: 20260921_0003
Revises: 20260921_0002
Create Date: 2026-09-21 00:02:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260921_0003"
down_revision: str | None = "20260921_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

case_status = postgresql.ENUM(
    "OPEN", "CLOSED", "ARCHIVED", name="legal_case_status", create_type=False
)
obligation_type = postgresql.ENUM(
    "DO",
    "PAY",
    "REFRAIN",
    "RESOLVE_REQUEST",
    "ISSUE_DOCUMENT",
    "OTHER",
    name="obligation_type",
    create_type=False,
)
obligation_status = postgresql.ENUM(
    "DRAFT",
    "OPEN",
    "IN_PROGRESS",
    "AT_RISK",
    "OVERDUE",
    "COMPLETED",
    "CANCELLED",
    name="obligation_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM("OPEN", "CLOSED", "ARCHIVED", name="legal_case_status").create(
        bind, checkfirst=True
    )
    postgresql.ENUM(
        "DO", "PAY", "REFRAIN", "RESOLVE_REQUEST", "ISSUE_DOCUMENT", "OTHER", name="obligation_type"
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "DRAFT",
        "OPEN",
        "IN_PROGRESS",
        "AT_RISK",
        "OVERDUE",
        "COMPLETED",
        "CANCELLED",
        name="obligation_status",
    ).create(bind, checkfirst=True)
    op.create_table(
        "legal_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column("case_number", sa.String(100), nullable=False),
        sa.Column("court", sa.String(255), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("status", case_status, nullable=False),
        sa.Column("external_reference", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "case_number", name="uq_legal_cases_tenant_number"),
    )
    op.create_index("ix_legal_cases_tenant_id", "legal_cases", ["tenant_id"])
    op.create_table(
        "court_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision_number", sa.String(100), nullable=False),
        sa.Column("decision_date", sa.Date(), nullable=False),
        sa.Column("final_date", sa.Date(), nullable=True),
        sa.Column("decision_type", sa.String(100), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "tenant_id", "case_id", "decision_number", name="uq_decisions_tenant_case_number"
        ),
    )
    op.create_index("ix_court_decisions_tenant_id", "court_decisions", ["tenant_id"])
    op.create_index("ix_court_decisions_case_id", "court_decisions", ["case_id"])
    op.create_table(
        "legal_obligations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "court_decision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("court_decisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("obligation_type", obligation_type, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "responsible_department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "responsible_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", obligation_status, nullable=False),
        sa.Column("completion_date", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    for column in (
        "tenant_id",
        "court_decision_id",
        "responsible_department_id",
        "responsible_user_id",
        "due_date",
    ):
        op.create_index(f"ix_legal_obligations_{column}", "legal_obligations", [column])
    op.create_table(
        "obligation_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "obligation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("legal_obligations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("old_status", obligation_status, nullable=True),
        sa.Column("new_status", obligation_status, nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_obligation_status_history_tenant_id", "obligation_status_history", ["tenant_id"]
    )
    op.create_index(
        "ix_obligation_status_history_obligation_id", "obligation_status_history", ["obligation_id"]
    )


def downgrade() -> None:
    op.drop_table("obligation_status_history")
    op.drop_table("legal_obligations")
    op.drop_table("court_decisions")
    op.drop_table("legal_cases")
    bind = op.get_bind()
    obligation_status.drop(bind, checkfirst=True)
    obligation_type.drop(bind, checkfirst=True)
    case_status.drop(bind, checkfirst=True)
