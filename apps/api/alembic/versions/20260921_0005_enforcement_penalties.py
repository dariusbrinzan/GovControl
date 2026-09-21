"""Create enforcement proceedings and penalty rules.

Revision ID: 20260921_0005
Revises: 20260921_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260921_0005"
down_revision: str | None = "20260921_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status = postgresql.ENUM(
        "OPEN", "SUSPENDED", "CLOSED", name="enforcement_status", create_type=False
    )
    postgresql.ENUM("OPEN", "SUSPENDED", "CLOSED", name="enforcement_status").create(
        op.get_bind(), checkfirst=True
    )
    op.create_table(
        "enforcement_proceedings",
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
        sa.Column("file_number", sa.String(100), nullable=False),
        sa.Column("enforcement_officer", sa.String(255)),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.UniqueConstraint("tenant_id", "file_number", name="uq_enforcement_tenant_file"),
    )
    op.create_index(
        "ix_enforcement_proceedings_tenant_id", "enforcement_proceedings", ["tenant_id"]
    )
    op.create_index(
        "ix_enforcement_proceedings_obligation_id", "enforcement_proceedings", ["obligation_id"]
    )
    op.create_table(
        "penalty_rules",
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
        sa.Column("calculation_type", sa.String(32), nullable=False),
        sa.Column("daily_amount", sa.Numeric(14, 2)),
        sa.Column("percentage", sa.Numeric(8, 4)),
        sa.Column("base_value", sa.Numeric(14, 2)),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date()),
    )
    op.create_index("ix_penalty_rules_tenant_id", "penalty_rules", ["tenant_id"])
    op.create_index("ix_penalty_rules_obligation_id", "penalty_rules", ["obligation_id"])


def downgrade() -> None:
    op.drop_table("penalty_rules")
    op.drop_table("enforcement_proceedings")
    postgresql.ENUM(
        "OPEN", "SUSPENDED", "CLOSED", name="enforcement_status", create_type=False
    ).drop(op.get_bind(), checkfirst=True)
