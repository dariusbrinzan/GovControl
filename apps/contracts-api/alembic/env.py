import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import contracts_app.models  # noqa: F401
from alembic import context
from contracts_app.config import get_settings
from contracts_app.database import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", get_settings().contracts_database_url)
target_metadata = Base.metadata


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    """Prevent this migration chain from observing or changing another service's schema."""
    if type_ == "schema":
        return name == "contracts"
    schema_name = parent_names.get("schema_name")
    return schema_name in {None, "contracts"}


def configure(connection: Connection | None = None) -> None:
    options: dict[str, object] = {
        "target_metadata": target_metadata,
        "compare_type": True,
        "include_schemas": True,
        "include_name": include_name,
        "version_table": "alembic_version_contracts",
    }
    if connection is None:
        options.update(
            url=config.get_main_option("sqlalchemy.url"),
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
        )
    else:
        options["connection"] = connection
    context.configure(**options)


def run_migrations_offline() -> None:
    configure()
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
