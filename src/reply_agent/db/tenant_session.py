"""Row-level security for the web-facing surface (Doc 2 §7 flagged this as a pre-real-data gap
— app-layer isolation, auth/dependencies.py, existed but nothing enforced it at the database
itself). Scope: api/dashboard.py, api/onboarding.py, api/knowledge.py, api/orders.py — the
routes reachable from an authenticated request where a forgotten business_id filter would be a
real, request-triggerable tenant leak. The LangGraph pipeline (worker.py, graph/nodes/*) still
uses db/session.py's plain get_sessionmaker() — its business_id always comes from a trusted
internal lookup (a Meta webhook's own identifiers resolving to a business), never a value an
outside request supplies directly to a query, so it isn't the same class of risk. Bringing the
whole pipeline under RLS too is a legitimate follow-up, not this one — see
migrations/versions/325e6d70b285_*.py for the full reasoning and the policies themselves.

Usage: routes that already resolve `business` via auth/dependencies.py's require_business_access
open their session with tenant_session(business.id) instead of get_sessionmaker()() — everything
else about using the session is identical.
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
