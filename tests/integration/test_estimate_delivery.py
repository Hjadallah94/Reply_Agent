"""graph/nodes/estimate_delivery.py (Doc 2 Section 9.1) — the agent's first live-tool-calling
capability. Real DB (tenant_session, Order/Business/Customer rows), mocked Anthropic extraction
and Google Maps (same reasoning as test_corrections.py mocking embed_documents — no real API
calls in the automated suite; the live-verification pass proves the real integrations
separately, per the plan's own note that Maps costs real money unlike everything else tested
this session).
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
    Customer,
    Order,
    OrderConfirmationStatus,
    PlanTier,
)
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.nodes.estimate_delivery import OrderExtraction, estimate_delivery

AMMAN_TZ = ZoneInfo("Asia/Amman")


@pytest.fixture
async def business():
    async with get_sessionmaker()() as session:
        b = Business(
            name="Estimate Delivery Test Cookie Co",
            plan_tier=PlanTier.starter,
            address="Jabal Amman, 3rd Circle, Amman",
            delivery_rules={"cutoff_hour": 15, "min_lead_hours": 6},
        )
        session.add(b)
        await session.commit()
        await session.refresh(b)
        yield b
        await session.execute(delete(Order).where(Order.business_id == b.id))
        await session.execute(delete(Customer).where(Customer.business_id == b.id))
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


@pytest.fixture
async def customer(business):
    async with get_sessionmaker()() as session:
        c = Customer(
            business_id=business.id, channel=ChannelType.whatsapp, channel_handle="962790001111"
        )
        session.add(c)
        await session.commit()
        await session.refresh(c)
        yield c


def _state(business_id: uuid.UUID, customer_id: uuid.UUID, text: str) -> dict:
    return {
        "business_id": str(business_id),
        "customer_id": str(customer_id),
        "channel": "whatsapp",
        "thread_id": "whatsapp:business:customer",
        "message": {
            "text": text,
            "media_refs": [],
            "received_at": "2026-08-28T12:00:00Z",
            "channel_message_id": "wamid.test",
        },
        "conversation_history": [],
        "customer_profile": {"past_orders": [], "preferences": {}, "prior_escalations": 0},
        "intent": {"label": "place_order", "confidence": 0.9, "sentiment": "neutral"},
    }


async def test_non_place_order_intent_is_a_noop():
    state = {
        "intent": {"label": "product_availability_price", "confidence": 0.9, "sentiment": "neutral"}
    }
    assert await estimate_delivery(state) == {}


async def test_after_cutoff_defers_to_next_day_and_creates_a_pending_confirmation_order(
    business, customer
):
    """Doc 3 roadmap (order confirmation layer): unlike before, this path now DOES cost an
    extraction call (needed for the Order row below) — only the Maps call stays free, since a
    past-cutoff order never needs a live transit estimate."""
    late_time = datetime(2026, 8, 28, 16, 0, tzinfo=AMMAN_TZ)  # 4pm, past the 3pm cutoff
    state = _state(business.id, customer.id, "I'd like to order 2 boxes of chocolate chip")

    with patch("reply_agent.graph.nodes.estimate_delivery.datetime") as mock_dt:
        mock_dt.now.return_value = late_time
        with (
            patch(
                "reply_agent.graph.nodes.estimate_delivery._extract_order_details",
                new=AsyncMock(
                    return_value=OrderExtraction(
                        product_count=2, delivery_address="Sweifieh, Amman"
                    )
                ),
            ) as mock_extract,
            patch(
                "reply_agent.graph.nodes.estimate_delivery.estimate_transit_minutes"
            ) as mock_maps,
        ):
            result = await estimate_delivery(state)

    assert result["delivery_estimate"]["same_day_eligible"] is False
    assert result["delivery_estimate"]["estimated_window"] == "tomorrow"
    assert result["delivery_estimate"]["order_reference"]
    mock_extract.assert_called_once()
    # The Maps call is still free — a past-cutoff order never needs a live transit estimate.
    mock_maps.assert_not_called()

    async with get_sessionmaker()() as session:
        order = await session.scalar(select(Order).where(Order.business_id == business.id))
        assert order is not None
        assert order.confirmation_status == OrderConfirmationStatus.pending
        assert order.delivery_window_promised == "tomorrow"


async def test_before_cutoff_with_no_address_is_a_capability_gap(business, customer):
    early_time = datetime(2026, 8, 28, 11, 0, tzinfo=AMMAN_TZ)
    state = _state(business.id, customer.id, "I'd like to order 2 boxes of chocolate chip")

    with patch("reply_agent.graph.nodes.estimate_delivery.datetime") as mock_dt:
        mock_dt.now.return_value = early_time
        with patch(
            "reply_agent.graph.nodes.estimate_delivery._extract_order_details",
            new=AsyncMock(return_value=OrderExtraction(product_count=2, delivery_address=None)),
        ):
            result = await estimate_delivery(state)

    assert result == {"delivery_estimate": None}


async def test_before_cutoff_computes_estimate_and_backlog_grows_across_orders(business, customer):
    early_time = datetime(2026, 8, 28, 11, 0, tzinfo=AMMAN_TZ)
    state = _state(business.id, customer.id, "2 boxes of chocolate chip to Sweifieh please")

    with patch("reply_agent.graph.nodes.estimate_delivery.datetime") as mock_dt:
        mock_dt.now.return_value = early_time

        with (
            patch(
                "reply_agent.graph.nodes.estimate_delivery._extract_order_details",
                new=AsyncMock(
                    return_value=OrderExtraction(
                        product_count=2, delivery_address="Sweifieh, Amman"
                    )
                ),
            ),
            patch(
                "reply_agent.graph.nodes.estimate_delivery.estimate_transit_minutes",
                new=AsyncMock(return_value=45),
            ) as mock_maps,
        ):
            first = await estimate_delivery(state)
            second = await estimate_delivery(state)

    assert first["delivery_estimate"]["same_day_eligible"] is True
    assert second["delivery_estimate"]["same_day_eligible"] is True
    mock_maps.assert_called_with(business.address, "Sweifieh, Amman")

    # The second call's backlog (Doc 2 Section 9.1 step 3) includes the first call's own Order
    # row — proving backlog-awareness is real, not per-message in isolation, matching the
    # plan's live-verification step 4.
    async with get_sessionmaker()() as session:
        orders = (
            await session.scalars(select(Order).where(Order.business_id == business.id))
        ).all()
        assert len(orders) == 2
        assert all(o.delivery_status == "pending" for o in orders)
        assert all(o.confirmation_status == OrderConfirmationStatus.pending for o in orders)
