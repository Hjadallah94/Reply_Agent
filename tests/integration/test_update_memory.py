"""graph/nodes/update_memory.py — the outbound-Message write (existing behavior, still
covered indirectly by other test files) plus the new order-confirmation-follow-up scheduling
(Doc 3 roadmap): stamping Order.confirmation_sent_at and enqueueing the nudge job, but only
when this send was actually a confirmation-request draft. Mocked enqueue_order_confirmation_nudge
throughout — no real Redis needed.
"""

import uuid
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

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
    Order,
    OrderConfirmationStatus,
    PlanTier,
)
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.nodes.update_memory import update_memory

AMMAN_TZ = ZoneInfo("Asia/Amman")
CUSTOMER_PHONE = "962790005555"
THREAD_ID_TEMPLATE = "whatsapp:{business_id}:" + CUSTOMER_PHONE


@pytest.fixture
async def business():
    async with get_sessionmaker()() as session:
        b = Business(name="Update Memory Test Cookie Co", plan_tier=PlanTier.starter)
        session.add(b)
        await session.commit()
        await session.refresh(b)
        yield b
        await session.execute(delete(Order).where(Order.business_id == b.id))
        await session.execute(
            delete(Message).where(
                Message.conversation_id.in_(
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
            business_id=business.id, channel=ChannelType.whatsapp, channel_handle=CUSTOMER_PHONE
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


async def _seed_order(business_id: uuid.UUID, *, order_reference: str) -> Order:
    async with get_sessionmaker()() as session:
        order = Order(
            business_id=business_id,
            order_reference=order_reference,
            customer_phone=CUSTOMER_PHONE,
            status="pending_delivery_estimate",
            items_summary="1 item(s)",
            order_date=datetime.now(AMMAN_TZ),
            delivery_address="Sweifieh, Amman",
            delivery_window_promised="3-4 hours",
            delivery_status="pending",
            confirmation_status=OrderConfirmationStatus.pending,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


def _base_state(business_id: uuid.UUID, thread_id: str) -> dict:
    return {
        "business_id": str(business_id),
        "thread_id": thread_id,
        "message": {"text": "1 box of 6 please", "channel_message_id": "wamid.test"},
        "draft_reply": {"text": "Here's what I understood...", "model_used": "haiku"},
        "route": "send",
        "intent": {"label": "place_order", "confidence": 0.9, "sentiment": "neutral"},
    }


async def test_confirmation_request_send_stamps_sent_at_and_enqueues_nudge(business, conversation):
    order = await _seed_order(business.id, order_reference="chat-abc123")
    state = _base_state(business.id, conversation.thread_id)
    state["require_order_confirmation"] = True
    state["delivery_estimate"] = {
        "same_day_eligible": True,
        "estimated_window": "3-4 hours",
        "reasoning": "quiet day",
        "order_reference": "chat-abc123",
    }

    with patch(
        "reply_agent.graph.nodes.update_memory.enqueue_order_confirmation_nudge"
    ) as mock_enqueue:
        await update_memory(state)

    mock_enqueue.assert_called_once_with(str(order.id))

    async with get_sessionmaker()() as session:
        refreshed = await session.get(Order, order.id)
        assert refreshed.confirmation_sent_at is not None


async def test_normal_send_does_not_touch_any_order_or_enqueue(business, conversation):
    order = await _seed_order(business.id, order_reference="chat-untouched")
    state = _base_state(business.id, conversation.thread_id)
    # No require_order_confirmation, no delivery_estimate — an ordinary answer, not a
    # confirmation-request draft.

    with patch(
        "reply_agent.graph.nodes.update_memory.enqueue_order_confirmation_nudge"
    ) as mock_enqueue:
        await update_memory(state)

    mock_enqueue.assert_not_called()

    async with get_sessionmaker()() as session:
        refreshed = await session.get(Order, order.id)
        assert refreshed.confirmation_sent_at is None


async def test_escalated_route_does_not_write_a_message_or_enqueue(business, conversation):
    state = _base_state(business.id, conversation.thread_id)
    state["route"] = "escalate"
    state["require_order_confirmation"] = True
    state["delivery_estimate"] = {
        "same_day_eligible": True,
        "estimated_window": "3-4 hours",
        "reasoning": "quiet day",
        "order_reference": "chat-abc123",
    }

    with patch(
        "reply_agent.graph.nodes.update_memory.enqueue_order_confirmation_nudge"
    ) as mock_enqueue:
        result = await update_memory(state)

    assert result == {}
    mock_enqueue.assert_not_called()

    async with get_sessionmaker()() as session:
        outbound = await session.scalar(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.direction == MessageDirection.outbound,
            )
        )
        assert outbound is None


async def test_confirmation_request_with_no_matching_order_does_not_crash_or_enqueue(
    business, conversation
):
    state = _base_state(business.id, conversation.thread_id)
    state["require_order_confirmation"] = True
    state["delivery_estimate"] = {
        "same_day_eligible": True,
        "estimated_window": "3-4 hours",
        "reasoning": "quiet day",
        "order_reference": "chat-does-not-exist",
    }

    with patch(
        "reply_agent.graph.nodes.update_memory.enqueue_order_confirmation_nudge"
    ) as mock_enqueue:
        result = await update_memory(state)

    assert result == {}
    mock_enqueue.assert_not_called()
