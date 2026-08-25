"""Row-level security itself (migrations/versions/325e6d70b285_*.py) — proves the database
enforces tenant isolation independently of application code, not just that the existing routes
happen to filter correctly. Real DB, using tenant_session directly (not through HTTP), so a
forgotten .where(business_id == ...) in some future route can't silently bypass this.
"""

import pytest
from sqlalchemy import delete, select

from reply_agent.db.models import Business, KnowledgeDocType, KnowledgeDocument, PlanTier
from reply_agent.db.session import get_sessionmaker
from reply_agent.db.tenant_session import get_app_sessionmaker, tenant_session


@pytest.fixture
async def two_businesses_with_docs():
    async with get_sessionmaker()() as session:
        business_a = Business(name="RLS Test Business A", plan_tier=PlanTier.starter)
        business_b = Business(name="RLS Test Business B", plan_tier=PlanTier.starter)
        session.add_all([business_a, business_b])
        await session.flush()

        session.add_all(
            [
                KnowledgeDocument(
                    business_id=business_a.id,
                    type=KnowledgeDocType.faq,
                    content="Business A's secret FAQ",
                ),
                KnowledgeDocument(
                    business_id=business_b.id,
                    type=KnowledgeDocType.faq,
                    content="Business B's secret FAQ",
                ),
            ]
        )
        await session.commit()
        await session.refresh(business_a)
        await session.refresh(business_b)

    yield business_a, business_b

    async with get_sessionmaker()() as session:
        await session.execute(
            delete(Business).where(Business.id.in_([business_a.id, business_b.id]))
        )
        await session.commit()


async def test_tenant_session_sees_only_its_own_business(two_businesses_with_docs):
    business_a, _business_b = two_businesses_with_docs

    # Deliberately no business_id filter at all — the exact class of bug this exists to catch.
    async with tenant_session(business_a.id) as session:
        docs = (await session.scalars(select(KnowledgeDocument))).all()

    assert [d.content for d in docs] == ["Business A's secret FAQ"]


async def test_tenant_session_cannot_see_a_different_businesss_docs(two_businesses_with_docs):
    _business_a, business_b = two_businesses_with_docs

    async with tenant_session(business_b.id) as session:
        docs = (await session.scalars(select(KnowledgeDocument))).all()

    assert [d.content for d in docs] == ["Business B's secret FAQ"]


async def test_no_context_set_sees_nothing(two_businesses_with_docs):
    """Fail-closed: querying the RLS-enforced role with no tenant context set at all (a bug in
    tenant_session itself, or code that bypasses it) returns zero rows, not every business's
    data.
    """
    async with get_app_sessionmaker()() as session:
        docs = (await session.scalars(select(KnowledgeDocument))).all()

    assert docs == []


async def test_cannot_read_another_businesss_row_by_primary_key(two_businesses_with_docs):
    """RLS applies even to a direct get-by-id, not just filtered listings."""
    _business_a, business_b = two_businesses_with_docs

    async with get_sessionmaker()() as session:
        doc_b = await session.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.business_id == business_b.id)
        )

    async with tenant_session(_business_a.id) as session:
        result = await session.get(KnowledgeDocument, doc_b.id)

    assert result is None
