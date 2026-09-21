import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.security import CurrentUserDependency

router = APIRouter(prefix="/auth")


class CurrentUserResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    display_name: str
    permissions: list[str]


@router.get("/me", response_model=CurrentUserResponse)
async def get_me(current_user: CurrentUserDependency) -> CurrentUserResponse:
    """Return the authenticated tenant context and effective permissions."""
    return CurrentUserResponse(
        id=current_user.id,
        tenant_id=current_user.tenant_id,
        email=current_user.email,
        display_name=current_user.display_name,
        permissions=sorted(current_user.permissions),
    )
