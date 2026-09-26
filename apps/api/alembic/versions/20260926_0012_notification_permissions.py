"""Add GovNotifications permissions and default system-role grants.

Revision ID: 20260926_0012
Revises: 20260926_0011
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260926_0012"
down_revision: str | None = "20260926_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "notifications.read": "View tenant notifications for the current user.",
    "notifications.manage": "Update notification state for the current user.",
    "notifications.preferences": "Manage notification preferences for the current user.",
    "notifications.admin": "Manage tenant notification templates and deliveries.",
    "notifications.audit": "View tenant notification audit events.",
}

ROLE_GRANTS = {
    "platform_admin": tuple(PERMISSIONS),
    "legal_director": tuple(PERMISSIONS),
    "contracts_manager": tuple(PERMISSIONS),
    "legal_officer": (
        "notifications.read",
        "notifications.manage",
        "notifications.preferences",
    ),
    "contracts_officer": (
        "notifications.read",
        "notifications.manage",
        "notifications.preferences",
    ),
    "auditor": ("notifications.read", "notifications.audit"),
}


def upgrade() -> None:
    for index, (key, description) in enumerate(PERMISSIONS.items(), start=1):
        permission_id = f"a0f00000-0000-4000-8000-{index:012d}"
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
