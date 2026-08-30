"""graph/nodes/request_owner_approval.py (Doc 2 Section 9.2) — mirrors escalate_to_owner.py's
shape: writes a row, notifies the owner, and the graph run ends there. Real DB (tenant_session,
Conversation/ApprovalRequest rows), mocked WhatsApp send — same pattern as
test_estimate_delivery.py mocking Google Maps.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from reply_agent.db.models import (
    ApprovalRequest,
    Business,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    PlanTier,
)
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.nodes.request_owner_approval import request_owner_approval

THREAD_ID_TEMPLATE = "whatsapp:{business_id}:962790003333"


@pytest.fixture
async def business():
    async with get_sessionmaker()() as session:
        b = Business(
            name="Request Owner Approval Test Cookie Co",
            plan_tier=PlanTier.starter,
            channels_connected={"whatsapp": {"phone_number_id": "test-phone-number-id"}},
        )
        session.add(b)
        await session.commit()
        await session.refresh(b)
        yield b
        await session.execute(
            delete(ApprovalRequest).where(
                ApprovalRequest.conversation_id.in_(
                    select(Conversation.id).where(Conversation.business_id == b.id)
                )
            )
        )
        await session.execute(delete(Conversation).where(Conversation.business_id == b.id))
        await session.execute(delete(Customer).where(Customer.business_id == b.id))
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


@pytest.fixture
async def conversation(business):
    async with get_sessionmaker()() as session:
        customer = Customer(
            business_id=business.id, channel=ChannelType.whatsapp, channel_handle="962790003333"
        )
        session.add(customer)
        await session.flush()

        conv = Conversation(
            business_id=business.id,
            channel=ChannelType.whatsapp,
            customer_id=customer.id,
            status=ConversationStatus.auto,
            thread_id=THREAD_ID_TEMPLATE.format(business_id=business.id),
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        yield conv


def _state(business_id: uuid.UUID, thread_id: str) -> dict:
    return {
        "business_id": str(business_id),
        "thread_id": thread_id,
        "message": {
            "text": "2 boxes of chocolate chip to Sweifieh please",
            "media_refs": [],
            "received_at": "2026-08-30T12:00:00Z",
            "channel_message_id": "wamid.test",
        },
        "draft_reply": {
            "text": "We can get that to you in 3-4 hours today.",
            "cited_sources": [],
            "model_used": "claude",
        },
        "delivery_estimate": {
            "same_day_eligible": True,
            "estimated_window": "3-4 hours",
            "reasoning": "0 order(s) already pending today, ~45 min transit time.",
            "order_reference": "chat-abcd1234",
        },
    }


async def test_writes_a_pending_approval_request_row(business, conversation):
    state = _state(business.id, conversation.thread_id)

    with patch("reply_agent.graph.nodes.request_owner_approval.send_text_message", new=AsyncMock()):
        await request_owner_approval(state)

    async with get_sessionmaker()() as session:
        approval = await session.scalar(
            select(ApprovalRequest).where(ApprovalRequest.conversation_id == conversation.id)
        )
        assert approval is not None
        assert approval.drafted_reply == "We can get that to you in 3-4 hours today."
        assert approval.reasoning == ("0 order(s) already pending today, ~45 min transit time.")
        assert approval.order_reference == "chat-abcd1234"
        assert approval.notified_at is not None

        refreshed_conversation = await session.get(Conversation, conversation.id)
        assert refreshed_conversation.status == ConversationStatus.owner_handled


async def test_returns_approve_route_and_approval_record(business, conversation):
    state = _state(business.id, conversation.thread_id)

    with patch("reply_agent.graph.nodes.request_owner_approval.send_text_message", new=AsyncMock()):
        result = await request_owner_approval(state)

    assert result["route"] == "approve"
    assert result["approval"]["reasoning"] == state["delivery_estimate"]["reasoning"]
    assert result["approval"]["drafted_reply"] == state["draft_reply"]["text"]
    assert result["approval"]["order_reference"] == "chat-abcd1234"


async def test_notifies_the_owner_when_a_notification_number_is_configured(business, conversation):
    state = _state(business.id, conversation.thread_id)

    with (
        patch(
            "reply_agent.graph.nodes.request_owner_approval.send_text_message", new=AsyncMock()
        ) as mock_send,
        patch("reply_agent.graph.nodes.request_owner_approval.get_settings") as mock_settings,
    ):
        mock_settings.return_value.owner_notification_whatsapp_number = "962790009999"
        await request_owner_approval(state)

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to"] == "962790009999"
    assert call_kwargs["phone_number_id"] == "test-phone-number-id"
    assert "3-4 hours" in call_kwargs["text"]
    assert "We can get that to you in 3-4 hours today." in call_kwargs["text"]


async def test_no_notification_when_owner_number_not_configured(business, conversation):
    state = _state(business.id, conversation.thread_id)

    with (
        patch(
            "reply_agent.graph.nodes.request_owner_approval.send_text_message", new=AsyncMock()
        ) as mock_send,
        patch("reply_agent.graph.nodes.request_owner_approval.get_settings") as mock_settings,
    ):
        mock_settings.return_value.owner_notification_whatsapp_number = ""
        await request_owner_approval(state)

    mock_send.assert_not_called()
