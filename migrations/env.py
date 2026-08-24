from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from reply_agent.config import get_settings
from reply_agent.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Alembic runs synchronously; use the psycopg (sync) URL rather than the app's asyncpg URL.
config.set_main_option("sqlalchemy.url", get_settings().database_url_sync)

# The LangGraph Postgres checkpointer (scripts/setup_checkpointer.py) owns its own tables in
# this same database — Alembic must never generate drop/create migrations for them.
_CHECKPOINTER_TABLES = {
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
    "checkpoint_migrations",
}


def include_object(object, name, type_, reflected, compare_to):  # noqa: A002
    if type_ == "table" and name in _CHECKPOINTER_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, include_object=include_object
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
