"""Owner dashboard (Doc 3 Phase 3). Real DB; the only thing mocked is the outbound channel
send, same pattern as tests/unit/test_send_reply.py.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from reply_agent.api.app import app
from reply_agent.db.models import (
    Business,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Escalation,
    EscalationStatus,
    Message,
    MessageDirection,
    PlanTier,
)
from reply_agent.db.session import get_engine, get_sessionmaker

BUSINESS_NAME = "Dashboard Test Business"


@pytest.fixture
async def escalation():
    async with get_sessionmaker()() as session:
        business = Business(name=BUSINESS_NAME, plan_tier=PlanTier.starter)
        session.add(business)
        await session.flush()

        customer = Customer(
            business_id=business.id,
            channel=ChannelType.whatsapp,
            channel_handle="962790001111",
        )
        session.add(customer)
        await session.flush()

        conversation = Conversation(
            business_id=business.id,
            channel=ChannelType.whatsapp,
            customer_id=customer.id,
            status=ConversationStatus.owner_handled,
            thread_id=f"whatsapp:{business.id}:962790001111",
        )
        session.add(conversation)
        await session.flush()

        session.add(
            Message(
                conversation_id=conversation.id,
                direction=MessageDirection.inbound,
                text="Can I get a refund?",
            )
        )

        escalation = Escalation(
            conversation_id=conversation.id,
            reason="refund_or_complaint always escalates",
            drafted_reply="Sorry, no cash refunds — exchanges only.",
            status=EscalationStatus.pending,
        )
        session.add(escalation)
        await session.commit()
        await session.refresh(escalation)

        yield business, escalation

        await session.execute(delete(Business).where(Business.id == business.id))
        await session.commit()


async def test_business_list_shows_pending_count(escalation):
    business, _ = escalation
    client = TestClient(app)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert business.name in response.text
    assert "1 pending" in response.text


async def test_business_dashboard_lists_the_escalation(escalation):
    business, esc = escalation
    client = TestClient(app)
    response = client.get(f"/businesses/{business.id}/dashboard")
    assert response.status_code == 200
    assert "962790001111" in response.text
    assert f"/dashboard/escalations/{esc.id}" in response.text


async def test_business_dashboard_404s_for_unknown_business():
    client = TestClient(app)
    response = client.get("/businesses/00000000-0000-0000-0000-000000000000/dashboard")
    assert response.status_code == 404


async def test_escalation_detail_shows_draft_and_reason(escalation):
    business, esc = escalation
    client = TestClient(app)
    response = client.get(f"/businesses/{business.id}/dashboard/escalations/{esc.id}")
    assert response.status_code == 200
    assert "refund_or_complaint always escalates" in response.text
    assert "Sorry, no cash refunds" in response.text
    assert "Can I get a refund?" in response.text


async def test_resolve_sends_updates_db_and_redirects(escalation):
    business, esc = escalation
    client = TestClient(app)

    with patch(
        "reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()
    ) as mock_send:
        response = client.post(
            f"/businesses/{business.id}/dashboard/escalations/{esc.id}/resolve",
            data={"reply_text": "Edited final reply"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/businesses/{business.id}/dashboard"
    mock_send.assert_called_once_with(to="962790001111", text="Edited final reply")

    await get_engine().dispose()

    async with get_sessionmaker()() as session:
        refreshed = await session.get(Escalation, esc.id)
        assert refreshed.status == EscalationStatus.resolved
        assert refreshed.resolved_by == "owner"
        assert refreshed.resolution_text == "Edited final reply"

        conversation = await session.get(Conversation, esc.conversation_id)
        assert conversation.status == ConversationStatus.auto

        outbound = await session.scalar(
            select(Message).where(
                Message.conversation_id == esc.conversation_id,
                Message.direction == MessageDirection.outbound,
            )
        )
        assert outbound.text == "Edited final reply"
        assert outbound.model_used == "owner"


async def test_resolve_already_resolved_returns_409(escalation):
    business, esc = escalation

    # Set up the "already resolved" state directly via the ORM rather than a prior HTTP call —
    # two TestClient calls in one test each spin their own event loop, and the connection pool
    # from the first breaks when the second reuses it (deeper than the dispose-between-calls
    # workaround used elsewhere in this file covers).
    async with get_sessionmaker()() as session:
        db_escalation = await session.get(Escalation, esc.id)
        db_escalation.status = EscalationStatus.resolved
        await session.commit()
    await get_engine().dispose()

    client = TestClient(app)
    with patch("reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()):
        response = client.post(
            f"/businesses/{business.id}/dashboard/escalations/{esc.id}/resolve",
            data={"reply_text": "Second attempt"},
        )

    assert response.status_code == 409


async def test_resolve_rejects_blank_reply(escalation):
    business, esc = escalation
    client = TestClient(app)
    response = client.post(
        f"/businesses/{business.id}/dashboard/escalations/{esc.id}/resolve",
        data={"reply_text": "   "},
    )
    assert response.status_code == 400
