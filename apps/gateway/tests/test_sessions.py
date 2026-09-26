from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import pytest

from gateway_app.config import Settings
from gateway_app.models import UserContext
from gateway_app.sessions import SessionStore


def user_context() -> UserContext:
    return UserContext(
        id="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000002",
        department_id=None,
        email="admin@govcontrol.local",
        display_name="Admin",
        roles=["platform_admin"],
        permissions=["legal.manage"],
    )


@pytest.mark.asyncio
async def test_session_cookie_is_opaque_signed_and_revocable() -> None:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = SessionStore(client, Settings())
    record = await store.create(user_context(), "local")
    cookie = store.encode_cookie(record.id)

    assert record.user.tenant_id not in cookie
    assert await store.resolve(cookie) is not None
    assert store.decode_cookie(f"{record.id}.forged") is None

    await store.destroy(record.id)
    assert await store.resolve(cookie) is None


@pytest.mark.asyncio
async def test_expired_session_is_rejected_and_rotation_changes_csrf() -> None:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    store = SessionStore(client, Settings(session_rotation_seconds=60))
    record = await store.create(user_context(), "local")
    rotated = await store.rotate(
        record.model_copy(update={"rotated_at": datetime.now(UTC) - timedelta(minutes=2)})
    )
    assert rotated.id != record.id
    assert rotated.csrf_token != record.csrf_token
    assert await store.resolve(store.encode_cookie(record.id)) is None

    expired = rotated.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    await client.set(
        f"{store.key_prefix}{expired.id}", expired.model_dump_json(), ex=300
    )
    assert await store.resolve(store.encode_cookie(expired.id)) is None
