"""Doc 3 roadmap (partner meeting 2026-09-01, order confirmation layer) — load_context.py's
pending-order lookup, classify_confirmation_reply.py's three-way decision + Order write, and
send_order_catalog_reply.py's terminal catalog reply. Real DB (tenant_session), mocked Anthropic
call (_classify_reply, same pattern as test_estimate_delivery.py mocking _extract_order_details)
and mocked WhatsApp send (same pattern as test_send_away_reply.py).
"""

import uuid
from datetime import datetime, timedelta
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
    KnowledgeDocType,
    KnowledgeDocument,
    Message,
    MessageDirection,
    Order,
    OrderConfirmationStatus,
    PlanTier,
)
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.nodes.classify_confirmation_reply import (
    ConfirmationDecision,
    classify_confirmation_reply,
)
from reply_agent.graph.nodes.load_context import load_context
from reply_agent.graph.nodes.send_order_catalog_reply import send_order_catalog_reply

AMMAN_TZ = ZoneInfo("Asia/Amman")
CUSTOMER_PHONE = "962790004444"
THREAD_ID_TEMPLATE = "whatsapp:{business_id}:" + CUSTOMER_PHONE


@pytest.fixture
async def business():
    async with get_sessionmaker()() as session:
        b = Business(
            name="Order Confirmation Test Cookie Co",
            plan_tier=PlanTier.starter,
            channels_connected={"whatsapp": {"phone_number_id": "test-phone-number-id"}},
        )
        session.add(b)
        await session.commit()
        await session.refresh(b)
        yield b
        await session.execute(delete(Order).where(Order.business_id == b.id))
        await session.execute(
            delete(KnowledgeDocument).where(KnowledgeDocument.business_id == b.id)
        )
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
        await session.refresh(conv, attribute_names=["id", "customer_id", "thread_id"])
        conv_customer_id = customer.id
        yield conv, conv_customer_id


async def _seed_order(
    business_id: uuid.UUID,
    *,
    confirmation_status: OrderConfirmationStatus | None,
    delivery_window_promised: str = "3-4 hours",
    order_date: datetime | None = None,
) -> Order:
    async with get_sessionmaker()() as session:
        order = Order(
            business_id=business_id,
            order_reference=f"chat-{uuid.uuid4().hex[:8]}",
            customer_phone=CUSTOMER_PHONE,
            status="pending_delivery_estimate",
            items_summary="2 item(s)",
            order_date=order_date or datetime.now(AMMAN_TZ),
            delivery_address="Sweifieh, Amman",
            delivery_window_promised=delivery_window_promised,
            delivery_status="pending",
            confirmation_status=confirmation_status,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


def _state(business_id: uuid.UUID, customer_id: uuid.UUID, thread_id: str, text: str) -> dict:
    return {
        "business_id": str(business_id),
        "customer_id": str(customer_id),
        "channel": "whatsapp",
        "thread_id": thread_id,
        "message": {
            "text": text,
            "media_refs": [],
            "received_at": "2026-09-01T12:00:00Z",
            "channel_message_id": "wamid.test",
        },
        "conversation_history": [],
    }


# --- load_context's pending-order lookup ---------------------------------------------------


async def test_load_context_surfaces_a_pending_order(business, conversation):
    conv, customer_id = conversation
    order = await _seed_order(business.id, confirmation_status=OrderConfirmationStatus.pending)
    state = _state(business.id, customer_id, conv.thread_id, "yes")

    result = await load_context(state)

    assert result["pending_order"] == {
        "id": str(order.id),
        "order_reference": order.order_reference,
        "delivery_window_promised": "3-4 hours",
    }


async def test_load_context_ignores_a_confirmed_order(business, conversation):
    conv, customer_id = conversation
    await _seed_order(business.id, confirmation_status=OrderConfirmationStatus.confirmed)
    state = _state(business.id, customer_id, conv.thread_id, "hi again")

    result = await load_context(state)

    assert result["pending_order"] is None


async def test_load_context_ignores_a_stale_pending_order(business, conversation):
    conv, customer_id = conversation
    stale = datetime.now(AMMAN_TZ) - timedelta(hours=25)
    await _seed_order(
        business.id, confirmation_status=OrderConfirmationStatus.pending, order_date=stale
    )
    state = _state(business.id, customer_id, conv.thread_id, "hello, do you have cookies?")

    result = await load_context(state)

    assert result["pending_order"] is None


# --- classify_confirmation_reply -----------------------------------------------------------


def _pending_order_state(business_id, customer_id, thread_id, order: Order, text: str) -> dict:
    state = _state(business_id, customer_id, thread_id, text)
    state["pending_order"] = {
        "id": str(order.id),
        "order_reference": order.order_reference,
        "delivery_window_promised": order.delivery_window_promised,
    }
    return state


async def test_classify_confirmation_reply_confirmed_reconstructs_state_and_updates_order(
    business, conversation
):
    conv, customer_id = conversation
    order = await _seed_order(
        business.id,
        confirmation_status=OrderConfirmationStatus.pending,
        delivery_window_promised="3-4 hours",
    )
    state = _pending_order_state(business.id, customer_id, conv.thread_id, order, "yes please")

    with patch(
        "reply_agent.graph.nodes.classify_confirmation_reply._classify_reply",
        new=AsyncMock(return_value=ConfirmationDecision(decision="confirmed", reason="clear yes")),
    ):
        result = await classify_confirmation_reply(state)

    assert result["order_confirmation_decision"] == "confirmed"
    assert result["intent"] == {"label": "place_order", "confidence": 1.0, "sentiment": "neutral"}
    assert result["delivery_estimate"] == {
        "same_day_eligible": True,
        "estimated_window": "3-4 hours",
        "reasoning": "Delivery estimate already confirmed with the customer.",
        "order_reference": order.order_reference,
    }

    async with get_sessionmaker()() as session:
        refreshed = await session.get(Order, order.id)
        assert refreshed.confirmation_status == OrderConfirmationStatus.confirmed


async def test_classify_confirmation_reply_confirmed_next_day_is_not_same_day_eligible(
    business, conversation
):
    conv, customer_id = conversation
    order = await _seed_order(
        business.id,
        confirmation_status=OrderConfirmationStatus.pending,
        delivery_window_promised="tomorrow",
    )
    state = _pending_order_state(business.id, customer_id, conv.thread_id, order, "yes")

    with patch(
        "reply_agent.graph.nodes.classify_confirmation_reply._classify_reply",
        new=AsyncMock(return_value=ConfirmationDecision(decision="confirmed", reason="yes")),
    ):
        result = await classify_confirmation_reply(state)

    assert result["delivery_estimate"]["same_day_eligible"] is False


async def test_classify_confirmation_reply_declined_updates_order(business, conversation):
    conv, customer_id = conversation
    order = await _seed_order(business.id, confirmation_status=OrderConfirmationStatus.pending)
    state = _pending_order_state(
        business.id, customer_id, conv.thread_id, order, "no, I meant something else"
    )

    with patch(
        "reply_agent.graph.nodes.classify_confirmation_reply._classify_reply",
        new=AsyncMock(
            return_value=ConfirmationDecision(decision="declined", reason="wants something else")
        ),
    ):
        result = await classify_confirmation_reply(state)

    assert result == {"order_confirmation_decision": "declined"}

    async with get_sessionmaker()() as session:
        refreshed = await session.get(Order, order.id)
        assert refreshed.confirmation_status == OrderConfirmationStatus.declined


async def test_classify_confirmation_reply_unclear_sets_escalation_override(business, conversation):
    conv, customer_id = conversation
    order = await _seed_order(business.id, confirmation_status=OrderConfirmationStatus.pending)
    state = _pending_order_state(business.id, customer_id, conv.thread_id, order, "hmm what?")

    with patch(
        "reply_agent.graph.nodes.classify_confirmation_reply._classify_reply",
        new=AsyncMock(return_value=ConfirmationDecision(decision="unclear", reason="ambiguous")),
    ):
        result = await classify_confirmation_reply(state)

    assert result["order_confirmation_decision"] == "unclear"
    assert result["escalation_override_reason"]

    async with get_sessionmaker()() as session:
        refreshed = await session.get(Order, order.id)
        assert refreshed.confirmation_status == OrderConfirmationStatus.escalated


# --- send_order_catalog_reply ---------------------------------------------------------------


async def test_send_order_catalog_reply_lists_products_and_sends(business, conversation):
    conv, customer_id = conversation
    async with get_sessionmaker()() as session:
        session.add(
            KnowledgeDocument(
                business_id=business.id,
                type=KnowledgeDocType.product,
                content="Product: Classic Chocolate Chip\nPrice: 6 JOD",
                structured_data={"name": "Classic Chocolate Chip"},
            )
        )
        await session.commit()

    state = _state(business.id, customer_id, conv.thread_id, "no thanks")

    with patch(
        "reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()
    ) as mock_send:
        result = await send_order_catalog_reply(state)

    assert result["route"] == "order_declined"
    assert "Classic Chocolate Chip" in result["draft_reply"]["text"]
    mock_send.assert_called_once()
    assert "Classic Chocolate Chip" in mock_send.call_args.kwargs["text"]

    async with get_sessionmaker()() as session:
        outbound = await session.scalar(
            select(Message).where(
                Message.conversation_id == conv.id,
                Message.direction == MessageDirection.outbound,
            )
        )
        assert outbound is not None
        assert "Classic Chocolate Chip" in outbound.text
        assert outbound.model_used == "order-confirmation-catalog"

        refreshed_conversation = await session.get(Conversation, conv.id)
        assert refreshed_conversation.status == ConversationStatus.auto


async def test_send_order_catalog_reply_handles_an_empty_catalog(business, conversation):
    conv, customer_id = conversation
    state = _state(business.id, customer_id, conv.thread_id, "no thanks")

    with patch("reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()):
        result = await send_order_catalog_reply(state)

    assert "(no products listed yet)" in result["draft_reply"]["text"]
