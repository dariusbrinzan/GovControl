from typing import cast

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.security import get_current_user
from app.db.session import AsyncSession


@pytest.mark.asyncio
async def test_development_auth_is_unavailable_when_disabled() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:password@localhost:5432/test",
        dev_auth_enabled=False,
    )

    with pytest.raises(HTTPException) as exception_info:
        await get_current_user(settings, cast(AsyncSession, object()), None)

    assert exception_info.value.status_code == 503


@pytest.mark.asyncio
async def test_development_auth_rejects_a_missing_bearer_token() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:password@localhost:5432/test",
        dev_auth_enabled=True,
        dev_auth_token="local-token",
        dev_auth_email="admin@govcontrol.local",
    )

    with pytest.raises(HTTPException) as exception_info:
        await get_current_user(settings, cast(AsyncSession, object()), None)

    assert exception_info.value.status_code == 401
