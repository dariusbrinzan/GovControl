import uuid
from typing import Any, cast

import pytest
from fastapi import HTTPException

from contracts_app.internal import internal_resource
from contracts_app.schemas import UserContext


@pytest.mark.asyncio
async def test_internal_resource_rejects_cross_tenant_before_query() -> None:
    user = UserContext(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        department_id=None,
        email="manager@example.test",
        display_name="Manager",
        roles=["contracts_manager"],
        permissions=["documents.read"],
        authorization="Bearer assertion",
    )

    with pytest.raises(HTTPException) as exception_info:
        await internal_resource(
            "Contract",
            uuid.uuid4(),
            uuid.uuid4(),
            None,
            user,
            cast(Any, None),
        )

    assert exception_info.value.status_code == 404
