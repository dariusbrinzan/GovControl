from collections.abc import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from notifications_app.config import get_settings


class Base(DeclarativeBase):
    metadata = MetaData(schema="notifications")


engine = create_async_engine(
    get_settings().notifications_database_url, pool_pre_ping=True, pool_size=10, max_overflow=20
)
session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session
