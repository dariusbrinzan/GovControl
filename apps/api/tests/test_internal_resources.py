import uuid
from typing import Any, cast

import pytest
from fastapi import HTTPException

from app.api.v1.internal import validate_legal_resource
from app.core.security import AuthenticatedUser


@pytest.mark.asyncio
async def test_internal_resource_rejects_cross_tenant_before_query() -> None:
    user = AuthenticatedUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        department_id=None,
        email="officer@example.test",
        display_name="Officer",
        roles=frozenset({"legal_officer"}),
        permissions=frozenset({"documents.read"}),
    )

    with pytest.raises(HTTPException) as exception_info:
        await validate_legal_resource(
            "LegalCase",
            uuid.uuid4(),
            uuid.uuid4(),
            None,
            user,
            cast(Any, None),
        )

    assert exception_info.value.status_code == 404
