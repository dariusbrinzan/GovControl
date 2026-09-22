"""Add tenant-aware trigram indexes for GovLegal search.

Revision ID: 20260922_0008
Revises: 20260921_0007
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260922_0008"
down_revision: str | None = "20260921_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_legal_cases_tenant_case_number_trgm "
        "ON legal_cases USING gin ((case_number || ' ' || subject) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_legal_obligations_tenant_description_trgm "
        "ON legal_obligations USING gin (description gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_legal_obligations_tenant_description_trgm")
    op.execute("DROP INDEX IF EXISTS ix_legal_cases_tenant_case_number_trgm")
