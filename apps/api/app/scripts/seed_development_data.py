import asyncio

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.rbac import Permission, Role, RolePermission, RoleScope, UserRole
from app.models.tenant import Tenant
from app.models.user import User

DEVELOPMENT_TENANT_NAME = "GovControl Demo Municipality"
DEVELOPMENT_TENANT_SLUG = "govcontrol-demo"
DEVELOPMENT_ADMIN_EMAIL = "admin@govcontrol.local"
DEVELOPMENT_ADMIN_NAME = "GovControl Development Admin"
PLATFORM_ADMIN_ROLE_KEY = "platform_admin"
PLATFORM_MANAGE_PERMISSION_KEY = "platform.manage"
LEGAL_MANAGE_PERMISSION_KEY = "legal.manage"


async def seed_development_data() -> None:
    """Create an idempotent local tenant and administrator for development only."""
    async with async_session_factory() as session, session.begin():
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == DEVELOPMENT_TENANT_SLUG))
        if tenant is None:
            tenant = Tenant(name=DEVELOPMENT_TENANT_NAME, slug=DEVELOPMENT_TENANT_SLUG)
            session.add(tenant)
            await session.flush()

        permissions: list[Permission] = []
        for key, description in (
            (PLATFORM_MANAGE_PERMISSION_KEY, "Manage platform configuration within the tenant."),
            (LEGAL_MANAGE_PERMISSION_KEY, "Manage GovLegal records within the tenant."),
        ):
            permission = await session.scalar(select(Permission).where(Permission.key == key))
            if permission is None:
                permission = Permission(key=key, description=description)
                session.add(permission)
                await session.flush()
            permissions.append(permission)

        role = await session.scalar(
            select(Role).where(
                Role.scope == RoleScope.SYSTEM,
                Role.key == PLATFORM_ADMIN_ROLE_KEY,
            )
        )
        if role is None:
            role = Role(
                scope=RoleScope.SYSTEM,
                key=PLATFORM_ADMIN_ROLE_KEY,
                name="Platform Admin",
                description="Full platform permissions for local development.",
            )
            session.add(role)
            await session.flush()

        for permission in permissions:
            role_permission = await session.get(RolePermission, (role.id, permission.id))
            if role_permission is None:
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))

        user = await session.scalar(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == DEVELOPMENT_ADMIN_EMAIL,
            )
        )
        if user is None:
            user = User(
                tenant_id=tenant.id,
                email=DEVELOPMENT_ADMIN_EMAIL,
                display_name=DEVELOPMENT_ADMIN_NAME,
            )
            session.add(user)
            await session.flush()

        user_role = await session.get(UserRole, (user.id, role.id))
        if user_role is None:
            session.add(UserRole(user_id=user.id, role_id=role.id))


def main() -> None:
    asyncio.run(seed_development_data())


if __name__ == "__main__":
    main()
