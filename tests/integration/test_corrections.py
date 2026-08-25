"""knowledge/corrections.py in isolation — api/dashboard.py's resolve_escalation tests cover
the route-level wiring (when a correction is/isn't recorded); this covers what
record_owner_correction itself actually writes. Real DB, mocked embeddings (same reasoning as
test_knowledge_upload.py — no Voyage key in CI).
"""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import delete, select

from reply_agent.db.models import Business, KnowledgeDocType, KnowledgeDocument, PlanTier
from reply_agent.db.session import get_sessionmaker
from reply_agent.knowledge.corrections import record_owner_correction

FAKE_VECTOR = [0.0] * 1024


@pytest.fixture
async def business():
    async with get_sessionmaker()() as session:
        b = Business(name="Corrections Test Business", plan_tier=PlanTier.starter)
        session.add(b)
        await session.commit()
        await session.refresh(b)
        yield b
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


async def test_record_owner_correction_writes_a_brand_voice_document(business):
    escalation_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

    with patch(
        "reply_agent.knowledge.corrections.embed_documents", return_value=[FAKE_VECTOR]
    ) as mock_embed:
        async with get_sessionmaker()() as session:
            await record_owner_correction(
                session,
                business_id=business.id,
                customer_message="Do you ship to Irbid?",
                corrected_reply="Yes, 2 JOD delivery, arrives in 1-2 days.",
                escalation_id=escalation_id,
            )
            await session.commit()

    mock_embed.assert_called_once_with(
        ["Customer: Do you ship to Irbid?\nSeller: Yes, 2 JOD delivery, arrives in 1-2 days."]
    )

    async with get_sessionmaker()() as session:
        doc = await session.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.business_id == business.id)
        )
        assert doc.type == KnowledgeDocType.brand_voice
        assert doc.content == (
            "Customer: Do you ship to Irbid?\nSeller: Yes, 2 JOD delivery, arrives in 1-2 days."
        )
        assert doc.structured_data == {
            "source": "owner_correction",
            "escalation_id": str(escalation_id),
        }
        assert doc.embedding_vector is not None
