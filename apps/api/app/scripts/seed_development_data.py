import asyncio

from sqlalchemy import select

from app.db.session import async_session_factory
from app.models.rbac import Permission, Role, RolePermission, RoleScope, UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.scripts.seed_demo_legal_data import seed_demo_legal_data

DEVELOPMENT_TENANT_NAME = "GovControl Demo Municipality"
DEVELOPMENT_TENANT_SLUG = "govcontrol-demo"
DEVELOPMENT_ADMIN_EMAIL = "admin@govcontrol.local"
DEVELOPMENT_ADMIN_NAME = "GovControl Development Admin"
PLATFORM_ADMIN_ROLE_KEY = "platform_admin"
PLATFORM_MANAGE_PERMISSION_KEY = "platform.manage"
LEGAL_MANAGE_PERMISSION_KEY = "legal.manage"
LEGAL_REPORT_PERMISSION_KEY = "legal.report"
AUDIT_VIEW_PERMISSION_KEY = "audit.view"


async def seed_development_data() -> None:
    """Create an idempotent local tenant and administrator for development only."""
    async with async_session_factory() as session, session.begin():
        tenant = await session.scalar(select(Tenant).where(Tenant.slug == DEVELOPMENT_TENANT_SLUG))
        if tenant is None:
            tenant = Tenant(name=DEVELOPMENT_TENANT_NAME, slug=DEVELOPMENT_TENANT_SLUG)
            session.add(tenant)
            await session.flush()

        permissions: dict[str, Permission] = {}
        for key, description in (
            (PLATFORM_MANAGE_PERMISSION_KEY, "Manage platform configuration within the tenant."),
            (LEGAL_MANAGE_PERMISSION_KEY, "Manage GovLegal records within the tenant."),
            (LEGAL_REPORT_PERMISSION_KEY, "View tenant-scoped GovLegal analytics and reports."),
            (AUDIT_VIEW_PERMISSION_KEY, "View the tenant audit trail."),
        ):
            permission = await session.scalar(select(Permission).where(Permission.key == key))
            if permission is None:
                permission = Permission(key=key, description=description)
                session.add(permission)
                await session.flush()
            permissions[key] = permission

        roles: dict[str, Role] = {}
        role_definitions = (
            (
                PLATFORM_ADMIN_ROLE_KEY,
                "Administrator platformă",
                "Acces complet pentru administrarea locală.",
                tuple(permissions),
            ),
            (
                "legal_director",
                "Director juridic",
                "Gestionează activitatea juridică, rapoartele și auditul.",
                (
                    LEGAL_MANAGE_PERMISSION_KEY,
                    LEGAL_REPORT_PERMISSION_KEY,
                    AUDIT_VIEW_PERMISSION_KEY,
                ),
            ),
            (
                "legal_officer",
                "Consilier juridic",
                "Gestionează dosare, hotărâri și obligații.",
                (LEGAL_MANAGE_PERMISSION_KEY,),
            ),
            (
                "auditor",
                "Auditor",
                "Consultă rapoartele și jurnalul de audit.",
                (LEGAL_REPORT_PERMISSION_KEY, AUDIT_VIEW_PERMISSION_KEY),
            ),
        )
        for role_key, name, description, permission_keys in role_definitions:
            role = await session.scalar(
                select(Role).where(Role.scope == RoleScope.SYSTEM, Role.key == role_key)
            )
            if role is None:
                role = Role(
                    scope=RoleScope.SYSTEM,
                    key=role_key,
                    name=name,
                    description=description,
                )
                session.add(role)
                await session.flush()
            roles[role_key] = role
            for permission_key in permission_keys:
                permission = permissions[permission_key]
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

        administrator_role = roles[PLATFORM_ADMIN_ROLE_KEY]
        user_role = await session.get(UserRole, (user.id, administrator_role.id))
        if user_role is None:
            session.add(UserRole(user_id=user.id, role_id=administrator_role.id))

        await seed_demo_legal_data(session, tenant, user, roles)


def main() -> None:
    asyncio.run(seed_development_data())


if __name__ == "__main__":
    main()
