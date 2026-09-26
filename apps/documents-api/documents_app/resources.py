import uuid

import httpx
from fastapi import HTTPException, Request, status

from documents_app.config import Settings
from documents_app.models import ResourceType
from documents_app.observability import current_request_id

PLATFORM_RESOURCES = frozenset(
    {
        ResourceType.LEGAL_CASE,
        ResourceType.LEGAL_OBLIGATION,
        ResourceType.COURT_DECISION,
        ResourceType.ENFORCEMENT_PROCEEDING,
    }
)


async def validate_resource(
    request: Request,
    settings: Settings,
    authorization: str,
    tenant_id: uuid.UUID,
    resource_type: ResourceType,
    resource_id: uuid.UUID,
) -> None:
    base_url = (
        settings.platform_api_url
        if resource_type in PLATFORM_RESOURCES
        else settings.contracts_api_url
    ).rstrip("/")
    if settings.internal_service_token is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service auth is not configured.")
    headers = {
        "Authorization": authorization,
        "X-Service-Token": settings.internal_service_token.get_secret_value(),
        "X-Tenant-ID": str(tenant_id),
    }
    request_id = current_request_id()
    if request_id is not None:
        headers["X-Request-ID"] = str(request_id)
    try:
        response = await request.app.state.http_client.get(
            f"{base_url}/internal/resources/{resource_type.value}/{resource_id}", headers=headers
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Resource authority is unavailable."
        ) from exc
    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resource not found in this tenant.")
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication is required.")
    if response.status_code != status.HTTP_204_NO_CONTENT:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Resource could not be verified.")
