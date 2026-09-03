"""worker.py's send_order_confirmation_nudge / _send_order_confirmation_nudge_async (Doc 3
roadmap, order confirmation follow-up) — the delayed RQ job itself, not the scheduling side
(that's tests/unit/test_queue_tasks.py and tests/integration/test_update_memory.py). Real DB,
mocked WhatsApp send (same pattern as test_send_away_reply.py).
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch
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
from reply_agent.worker import _send_order_confirmation_nudge_async

AMMAN_TZ = ZoneInfo("Asia/Amman")
CUSTOMER_PHONE = "962790006666"
THREAD_ID_TEMPLATE = "whatsapp:{business_id}:" + CUSTOMER_PHONE


@pytest.fixture
async def business():
    async with get_sessionmaker()() as session:
        b = Business(
            name="Nudge Test Cookie Co",
            plan_tier=PlanTier.starter,
            channels_connected={"whatsapp": {"phone_number_id": "test-phone-number-id"}},
        )
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


async def _seed_order(
    business_id: uuid.UUID,
    *,
    confirmation_status: OrderConfirmationStatus,
    confirmation_nudge_sent_at: datetime | None = None,
    customer_phone: str = CUSTOMER_PHONE,
) -> Order:
    async with get_sessionmaker()() as session:
        order = Order(
            business_id=business_id,
            order_reference=f"chat-{uuid.uuid4().hex[:8]}",
            customer_phone=customer_phone,
            status="pending_delivery_estimate",
            items_summary="1 item(s)",
            order_date=datetime.now(AMMAN_TZ),
            delivery_address="Sweifieh, Amman",
            delivery_window_promised="3-4 hours",
            delivery_status="pending",
            confirmation_status=confirmation_status,
            confirmation_sent_at=datetime.now(AMMAN_TZ),
            confirmation_nudge_sent_at=confirmation_nudge_sent_at,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


async def test_sends_nudge_and_sets_guard_when_still_pending(business, conversation):
    order = await _seed_order(business.id, confirmation_status=OrderConfirmationStatus.pending)

    with patch(
        "reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()
    ) as mock_send:
        await _send_order_confirmation_nudge_async(str(order.id))

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["to"] == CUSTOMER_PHONE

    async with get_sessionmaker()() as session:
        refreshed = await session.get(Order, order.id)
        assert refreshed.confirmation_nudge_sent_at is not None

        outbound = await session.scalar(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.direction == MessageDirection.outbound,
            )
        )
        assert outbound is not None
        assert outbound.model_used == "order-confirmation-nudge"


async def test_no_op_when_order_already_confirmed(business, conversation):
    order = await _seed_order(business.id, confirmation_status=OrderConfirmationStatus.confirmed)

    with patch(
        "reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()
    ) as mock_send:
        await _send_order_confirmation_nudge_async(str(order.id))

    mock_send.assert_not_called()


async def test_no_op_when_already_nudged(business, conversation):
    order = await _seed_order(
        business.id,
        confirmation_status=OrderConfirmationStatus.pending,
        confirmation_nudge_sent_at=datetime.now(AMMAN_TZ),
    )

    with patch(
        "reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()
    ) as mock_send:
        await _send_order_confirmation_nudge_async(str(order.id))

    mock_send.assert_not_called()


async def test_no_op_when_order_does_not_exist():
    with patch(
        "reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()
    ) as mock_send:
        await _send_order_confirmation_nudge_async(str(uuid.uuid4()))

    mock_send.assert_not_called()


async def test_no_op_when_no_matching_whatsapp_customer(business, conversation):
    order = await _seed_order(
        business.id,
        confirmation_status=OrderConfirmationStatus.pending,
        customer_phone="962790009999",  # no Customer row with this handle exists
    )

    with patch(
        "reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()
    ) as mock_send:
        await _send_order_confirmation_nudge_async(str(order.id))

    mock_send.assert_not_called()
