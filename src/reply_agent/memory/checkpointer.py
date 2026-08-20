"""Postgres-backed LangGraph checkpointer (Doc 2 Section 2.3 / 4): durable per-thread state
so a crash or restart resumes mid-conversation instead of losing context.
"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from reply_agent.config import get_settings


def checkpointer_conn_string() -> str:
    # AsyncPostgresSaver connects via psycopg directly and expects a plain DSN,
    # not a SQLAlchemy dialect URL (postgresql+psycopg://...).
    return get_settings().database_url_sync.replace("postgresql+psycopg://", "postgresql://")


async def setup_checkpointer_tables() -> None:
    async with AsyncPostgresSaver.from_conn_string(checkpointer_conn_string()) as saver:
        await saver.setup()
