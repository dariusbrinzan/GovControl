import fakeredis.aioredis
import pytest
from redis.exceptions import ConnectionError

from notifications_app.config import Settings
from notifications_app.worker import consume_new, ensure_group, process_message

DATABASE_URL = "postgresql+asyncpg://user:password@localhost/database"


@pytest.mark.asyncio
async def test_consumer_group_creation_is_idempotent() -> None:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    settings = Settings(notifications_database_url=DATABASE_URL)
    await ensure_group(client, settings)
    await ensure_group(client, settings)
    groups = await client.xinfo_groups(settings.event_stream_name)
    assert groups[0]["name"] == settings.consumer_group
    await client.aclose()


@pytest.mark.asyncio
async def test_invalid_event_reaches_dead_letter_after_limit() -> None:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    settings = Settings(notifications_database_url=DATABASE_URL, max_delivery_attempts=2)
    await ensure_group(client, settings)
    message_id = await client.xadd(settings.event_stream_name, {"event": "not-json"})
    messages = await client.xreadgroup(
        settings.consumer_group,
        settings.consumer_name,
        {settings.event_stream_name: ">"},
        count=1,
    )
    fields = messages[0][1][0][1]
    assert await process_message(client, settings, message_id, fields) is False
    assert await client.get(f"govnotifications:retry:{message_id}:after") is not None
    await client.delete(f"govnotifications:retry:{message_id}:after")
    assert await process_message(client, settings, message_id, fields) is False
    dead = await client.xrange(settings.dead_letter_stream_name)
    assert len(dead) == 1
    assert dead[0][1]["source_message_id"] == message_id
    pending = await client.xpending(settings.event_stream_name, settings.consumer_group)
    assert pending["pending"] == 0
    await client.aclose()


@pytest.mark.asyncio
async def test_redis_outage_is_reported_to_worker_loop() -> None:
    class UnavailableRedis:
        async def xreadgroup(self, *args: object, **kwargs: object) -> object:
            raise ConnectionError("redis unavailable")

    settings = Settings(notifications_database_url=DATABASE_URL)
    with pytest.raises(ConnectionError, match="unavailable"):
        await consume_new(UnavailableRedis(), settings)  # type: ignore[arg-type]
