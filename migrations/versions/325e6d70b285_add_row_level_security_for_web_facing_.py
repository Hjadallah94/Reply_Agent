"""add row-level security for web-facing tenant tables

Revision ID: 325e6d70b285
Revises: 9d2c3cd4c158
Create Date: 2026-08-25 18:56:57.413062

Web-surface scope only (api/dashboard.py, api/onboarding.py, api/knowledge.py, api/orders.py) —
these are the routes reachable from an authenticated request where a forgotten business_id
filter would be a real, request-triggerable tenant leak. The LangGraph pipeline (worker.py and
graph/nodes/*) keeps using the reply_agent role/database_url — its business_id always comes from
a trusted internal lookup (Meta webhook -> business, never a value an outside request supplies
directly to a query), not the same class of risk, and bringing it under RLS too is a separate,
much larger change (db/tenant_session.py's docstring has the full reasoning).

Why a new role at all: the reply_agent role owns every table and is a Postgres superuser
(POSTGRES_USER in docker-compose.yml creates one) — RLS policies have literally no effect on a
superuser's queries, FORCE ROW LEVEL SECURITY included. Only a distinct, non-superuser role can
be constrained by RLS at all, so api/dashboard.py etc. connect as reply_agent_app instead
(db/tenant_session.py) for the tables covered here.

Tables with a direct business_id column (knowledge_documents, conversations, customers, orders,
subscriptions) get a straightforward policy. businesses itself is keyed by id, not business_id.
messages and escalations have no business_id column at all — reached only via
conversation_id -> conversations.business_id, so their policies join through that.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "325e6d70b285"
down_revision: str | None = "9d2c3cd4c158"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DIRECT_TABLES = ["knowledge_documents", "conversations", "customers", "orders", "subscriptions"]
_JOINED_TABLES = ["messages", "escalations"]
_ALL_RLS_TABLES = ["businesses", *_DIRECT_TABLES, *_JOINED_TABLES]

# current_setting(..., true) returns '' (not NULL) once a placeholder GUC has been set at least
# once in a session and then reset by a SET LOCAL's transaction ending — casting '' straight to
# ::uuid raises an error rather than failing closed. NULLIF converts that '' to a real NULL
# first, so an unset/reset context safely matches no rows instead of erroring the whole query.
_CURRENT_BUSINESS_ID = "NULLIF(current_setting('app.current_business_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'reply_agent_app') THEN
                CREATE ROLE reply_agent_app LOGIN PASSWORD 'reply_agent_app';
            END IF;
        END
        $$;
        """
    )
    # current_database() rather than a hardcoded name — the local dev DB is "reply_agent"
    # (docker-compose.yml), but a managed host (Neon, RDS, ...) will use whatever name it
    # assigns, so GRANT CONNECT ON DATABASE <literal name> isn't portable.
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('GRANT CONNECT ON DATABASE %I TO reply_agent_app', current_database());
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO reply_agent_app")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(_ALL_RLS_TABLES)} TO reply_agent_app"
    )

    # businesses: keyed by its own id, not a business_id column.
    op.execute("ALTER TABLE businesses ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE businesses FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON businesses
        USING (id = {_CURRENT_BUSINESS_ID})
        WITH CHECK (id = {_CURRENT_BUSINESS_ID})
        """
    )

    for table in _DIRECT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (business_id = {_CURRENT_BUSINESS_ID})
            WITH CHECK (business_id = {_CURRENT_BUSINESS_ID})
            """
        )

    for table in _JOINED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (
                EXISTS (
                    SELECT 1 FROM conversations
                    WHERE conversations.id = {table}.conversation_id
                    AND conversations.business_id = {_CURRENT_BUSINESS_ID}
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM conversations
                    WHERE conversations.id = {table}.conversation_id
                    AND conversations.business_id = {_CURRENT_BUSINESS_ID}
                )
            )
            """
        )


def downgrade() -> None:
    for table in _ALL_RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute(f"REVOKE ALL ON {', '.join(_ALL_RLS_TABLES)} FROM reply_agent_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM reply_agent_app")
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM reply_agent_app', current_database());
        END
        $$;
        """
    )
    op.execute("DROP ROLE IF EXISTS reply_agent_app")
