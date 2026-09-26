from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.models.user import User
from app.services.audit import AuditService


class FederatedIdentityUnavailableError(Exception):
    """Raised when an OIDC identity is not pre-provisioned or safely linkable."""


class IdentityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_federated_user(
        self,
        *,
        issuer: str,
        subject: str,
        email: str,
        email_verified: bool,
        allow_email_linking: bool,
    ) -> User:
        normalized_issuer = issuer.rstrip("/")
        user = await self._session.scalar(
            select(User)
            .join(Tenant, Tenant.id == User.tenant_id)
            .where(
                User.external_issuer == normalized_issuer,
                User.external_subject == subject,
                User.is_active.is_(True),
                Tenant.is_active.is_(True),
            )
        )
        if user is not None:
            return user
        if not allow_email_linking or not email_verified:
            raise FederatedIdentityUnavailableError

        candidates = list(
            (
                await self._session.scalars(
                    select(User)
                    .join(Tenant, Tenant.id == User.tenant_id)
                    .where(
                        func.lower(User.email) == email.lower(),
                        User.is_active.is_(True),
                        Tenant.is_active.is_(True),
                        User.external_subject.is_(None),
                    )
                    .limit(2)
                )
            ).all()
        )
        if len(candidates) != 1:
            raise FederatedIdentityUnavailableError
        user = candidates[0]
        user.external_issuer = normalized_issuer
        user.external_subject = subject
        AuditService(self._session).record_event(
            tenant_id=user.tenant_id,
            actor_user_id=user.id,
            action="FEDERATED_IDENTITY_LINKED",
            entity_type="User",
            entity_id=user.id,
            new_value={"issuer": normalized_issuer, "subject": subject},
        )
        await self._session.commit()
        await self._session.refresh(user)
        return user
