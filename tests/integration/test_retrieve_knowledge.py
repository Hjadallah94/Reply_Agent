"""graph/nodes/retrieve_knowledge.py's expiry filter (Doc 3 Phase 6.5) — an expired promotion
must stop surfacing even if it's still semantically relevant to a vector search. Real DB, no
HTTP layer, modeled on test_tenant_session.py's style; embed_query mocked to a fixed vector
(no real Voyage call), same reasoning as every other test mocking embeddings this session.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import delete

from reply_agent.db.models import Business, KnowledgeDocType, KnowledgeDocument, PlanTier
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.nodes.retrieve_knowledge import retrieve_knowledge

EMBEDDING_DIM = 1024


@pytest.fixture
async def business():
    async with get_sessionmaker()() as session:
        b = Business(name="Retrieve Knowledge Test Business", plan_tier=PlanTier.starter)
        session.add(b)
        await session.commit()
        await session.refresh(b)
        yield b
        await session.execute(
            delete(KnowledgeDocument).where(KnowledgeDocument.business_id == b.id)
        )
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


def _state(business_id) -> dict:
    return {
        "business_id": str(business_id),
        "message": {
            "text": "Any promotions running right now?",
            "media_refs": [],
            "received_at": "2026-08-31T12:00:00Z",
            "channel_message_id": "wamid.test",
        },
    }


async def test_expired_promotion_is_excluded_from_retrieval(business):
    now = datetime.now(UTC)
    async with get_sessionmaker()() as session:
        session.add_all(
            [
                KnowledgeDocument(
                    business_id=business.id,
                    type=KnowledgeDocType.promotion,
                    content="Promotion: Expired Sale\nDiscount: 50% off",
                    structured_data={"title": "Expired Sale", "discount_text": "50% off"},
                    active_from=now - timedelta(days=10),
                    active_until=now - timedelta(days=1),
                    embedding_vector=[0.1] * EMBEDDING_DIM,
                ),
                KnowledgeDocument(
                    business_id=business.id,
                    type=KnowledgeDocType.promotion,
                    content="Promotion: Active Sale\nDiscount: 20% off",
                    structured_data={"title": "Active Sale", "discount_text": "20% off"},
                    active_from=now - timedelta(days=1),
                    active_until=now + timedelta(days=5),
                    embedding_vector=[0.1] * EMBEDDING_DIM,
                ),
            ]
        )
        await session.commit()

    with patch(
        "reply_agent.graph.nodes.retrieve_knowledge.embed_query",
        return_value=[0.1] * EMBEDDING_DIM,
    ):
        result = await retrieve_knowledge(_state(business.id))

    snippets = [c["snippet"] for c in result["retrieved_context"]]
    assert any("Active Sale" in s for s in snippets)
    assert not any("Expired Sale" in s for s in snippets)


async def test_promotion_with_no_active_until_is_included(business):
    async with get_sessionmaker()() as session:
        session.add(
            KnowledgeDocument(
                business_id=business.id,
                type=KnowledgeDocType.promotion,
                content="Promotion: Ongoing Sale\nDiscount: 15% off",
                structured_data={"title": "Ongoing Sale", "discount_text": "15% off"},
                embedding_vector=[0.1] * EMBEDDING_DIM,
            )
        )
        await session.commit()

    with patch(
        "reply_agent.graph.nodes.retrieve_knowledge.embed_query",
        return_value=[0.1] * EMBEDDING_DIM,
    ):
        result = await retrieve_knowledge(_state(business.id))

    snippets = [c["snippet"] for c in result["retrieved_context"]]
    assert any("Ongoing Sale" in s for s in snippets)


async def test_non_promotion_documents_are_unaffected_by_the_date_filter(business):
    async with get_sessionmaker()() as session:
        session.add(
            KnowledgeDocument(
                business_id=business.id,
                type=KnowledgeDocType.faq,
                content="Q: Do you deliver?\nA: Yes, across Amman.",
                embedding_vector=[0.1] * EMBEDDING_DIM,
            )
        )
        await session.commit()

    with patch(
        "reply_agent.graph.nodes.retrieve_knowledge.embed_query",
        return_value=[0.1] * EMBEDDING_DIM,
    ):
        result = await retrieve_knowledge(_state(business.id))

    snippets = [c["snippet"] for c in result["retrieved_context"]]
    assert any("Do you deliver?" in s for s in snippets)
