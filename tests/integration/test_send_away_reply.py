"""graph/nodes/send_away_reply.py (Doc 3 roadmap, "I'm not available today") — real DB
(tenant_session, Conversation/Message rows), mocked WhatsApp send.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from reply_agent.db.models import (
    Business,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    PlanTier,
)
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.nodes.send_away_reply import DEFAULT_AWAY_MESSAGE, send_away_reply

THREAD_ID_TEMPLATE = "whatsapp:{business_id}:962790005555"


@pytest.fixture
async def business():
    async with get_sessionmaker()() as session:
        b = Business(
            name="Send Away Reply Test Business",
            plan_tier=PlanTier.starter,
            channels_connected={"whatsapp": {"phone_number_id": "test-phone-number-id"}},
        )
        session.add(b)
        await session.commit()
        await session.refresh(b)
        yield b
        await session.execute(delete(Conversation).where(Conversation.business_id == b.id))
        await session.execute(delete(Customer).where(Customer.business_id == b.id))
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


@pytest.fixture
async def conversation(business):
    async with get_sessionmaker()() as session:
        customer = Customer(
            business_id=business.id, channel=ChannelType.whatsapp, channel_handle="962790005555"
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
        "channel": "whatsapp",
        "thread_id": thread_id,
        "message": {
            "text": "Do you have any cookies left?",
            "media_refs": [],
            "received_at": "2026-09-01T12:00:00Z",
            "channel_message_id": "wamid.test",
        },
    }


async def test_sends_the_default_message_when_none_customized(business, conversation):
    state = _state(business.id, conversation.thread_id)

    with patch(
        "reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()
    ) as mock_send:
        result = await send_away_reply(state)

    assert result["route"] == "away"
    mock_send.assert_called_once_with(
        to="962790005555", text=DEFAULT_AWAY_MESSAGE, phone_number_id="test-phone-number-id"
    )

    async with get_sessionmaker()() as session:
        outbound = await session.scalar(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.direction == MessageDirection.outbound,
            )
        )
        assert outbound.text == DEFAULT_AWAY_MESSAGE
        assert outbound.model_used == "away-mode"

        refreshed_conversation = await session.get(Conversation, conversation.id)
        assert refreshed_conversation.status == ConversationStatus.auto


async def test_sends_the_business_custom_message_when_set(business, conversation):
    async with get_sessionmaker()() as session:
        db_business = await session.get(Business, business.id)
        db_business.is_away = True
        db_business.away_message = "We're closed for Eid, back Monday!"
        await session.commit()

    state = _state(business.id, conversation.thread_id)

    with patch(
        "reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()
    ) as mock_send:
        await send_away_reply(state)

    mock_send.assert_called_once_with(
        to="962790005555",
        text="We're closed for Eid, back Monday!",
        phone_number_id="test-phone-number-id",
    )
