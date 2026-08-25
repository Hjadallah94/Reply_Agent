"""Row-level security, database-enforced tenant isolation (Doc 2 §7 flagged this as a
pre-real-data gap — app-layer isolation existed, but nothing enforced it at the database
itself). Used everywhere a business_id is known: api/dashboard.py, api/onboarding.py,
api/knowledge.py, api/orders.py (where auth/dependencies.py's require_business_access resolves
it from a logged-in user), and worker.py plus every graph/nodes/* module (where it comes from
GraphState["business_id"], set once at the top of the pipeline by
context_resolution.find_business_by_channel_key's lookup — the one place that genuinely has to
search across every business, since which business owns a given webhook is exactly what that
lookup exists to determine). See migrations/versions/325e6d70b285_*.py for the policies
themselves and the reasoning behind the separate, non-superuser role this connects as (RLS has
no effect at all on the plain reply_agent role — it's a Postgres superuser).

Not covered: the LangGraph checkpointer (memory/checkpointer.py's AsyncPostgresSaver) — a
genuinely separate connection mechanism (psycopg via its own connection string, not this
SQLAlchemy session pattern) with its own internal tables that aren't part of db/models.py at
all and have no business_id column to filter on. Bringing it under RLS would be a distinct,
larger piece of work, not an extension of this one.

Usage: async with tenant_session(business_id) as session: — everything about using the session
after that is identical to the plain get_sessionmaker()() pattern it replaces.
"""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from reply_agent.config import get_settings


@lru_cache
def get_app_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url_app, pool_pre_ping=True)


@lru_cache
def get_app_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_app_engine(), expire_on_commit=False)


@asynccontextmanager
async def tenant_session(business_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    async with get_app_sessionmaker()() as session, session.begin():
        # set_config (not a plain SET LOCAL string) so this goes through normal parameter
        # binding — SET doesn't support bind parameters the way a regular statement does, and
        # string-formatting a UUID directly into SQL is the kind of thing this migration exists
        # to make unnecessary elsewhere. is_local=true mirrors SET LOCAL: resets at the end of
        # this transaction, so a pooled connection can never carry one request's tenant context
        # into the next.
        await session.execute(
            text("SELECT set_config('app.current_business_id', :business_id, true)"),
            {"business_id": str(business_id)},
        )
        yield session
