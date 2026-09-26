"""Add GovDocuments permissions and default system-role grants.

Revision ID: 20260926_0011
Revises: 20260925_0010
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260926_0011"
down_revision: str | None = "20260925_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "documents.read": "View tenant documents and their versions.",
    "documents.upload": "Upload documents and create document versions.",
    "documents.manage": "Manage document metadata, links and archival.",
    "documents.delete": "Soft-delete and restore documents.",
    "documents.audit": "View the tenant document audit trail.",
}

ROLE_GRANTS = {
    "platform_admin": tuple(PERMISSIONS),
    "legal_director": tuple(PERMISSIONS),
    "contracts_manager": tuple(PERMISSIONS),
    "legal_officer": ("documents.read", "documents.upload", "documents.manage"),
    "contracts_officer": ("documents.read", "documents.upload", "documents.manage"),
    "auditor": ("documents.read", "documents.audit"),
}


def upgrade() -> None:
    for index, (key, description) in enumerate(PERMISSIONS.items(), start=1):
        permission_id = f"d0c00000-0000-4000-8000-{index:012d}"
        op.execute(
            "INSERT INTO permissions (id, key, description) "
            f"VALUES ('{permission_id}', '{key}', '{description}') "
            "ON CONFLICT (key) DO NOTHING"
        )
    for role_key, permissions in ROLE_GRANTS.items():
        for permission in permissions:
            op.execute(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "SELECT roles.id, permissions.id FROM roles, permissions "
                f"WHERE roles.key = '{role_key}' AND permissions.key = '{permission}' "
                "ON CONFLICT DO NOTHING"
            )


def downgrade() -> None:
    permission_list = ", ".join(f"'{key}'" for key in PERMISSIONS)
    op.execute(
        "DELETE FROM role_permissions WHERE permission_id IN "
        f"(SELECT id FROM permissions WHERE key IN ({permission_list}))"
    )
    op.execute(f"DELETE FROM permissions WHERE key IN ({permission_list})")
