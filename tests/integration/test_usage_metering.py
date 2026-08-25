"""Message metering against Doc 5 Section 2's tier caps, wired into load_context.py at the same
idempotent insert used for webhook-redelivery dedup. Real DB; load_context itself makes no LLM/
embedding calls, so nothing needs mocking here.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from reply_agent.billing.usage import get_or_create_subscription
from reply_agent.db.models import (
    Business,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    PlanTier,
    Subscription,
)
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.context_resolution import build_thread_id
from reply_agent.graph.nodes.load_context import load_context

BUSINESS_NAME = "Usage Metering Test Business"


@pytest.fixture
async def conversation():
    async with get_sessionmaker()() as session:
        business = Business(name=BUSINESS_NAME, plan_tier=PlanTier.starter)
        session.add(business)
        await session.flush()

        customer = Customer(
            business_id=business.id,
            channel=ChannelType.whatsapp,
            channel_handle="962790002222",
        )
        session.add(customer)
        await session.flush()

        thread_id = build_thread_id(business.id, ChannelType.whatsapp, "962790002222")
        conversation = Conversation(
            business_id=business.id,
            channel=ChannelType.whatsapp,
            customer_id=customer.id,
            status=ConversationStatus.auto,
            thread_id=thread_id,
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)

        yield business, conversation

        await session.execute(delete(Business).where(Business.id == business.id))
        await session.commit()


def _state(business_id, thread_id: str, text: str, channel_message_id: str) -> dict:
    return {
        "business_id": str(business_id),
        "thread_id": thread_id,
        "message": {"text": text, "channel_message_id": channel_message_id},
    }


async def test_new_message_creates_subscription_and_increments_usage(conversation):
    business, convo = conversation

    await load_context(_state(business.id, convo.thread_id, "hello", "wamid-usage-1"))

    async with get_sessionmaker()() as session:
        subscription = await session.get(Subscription, business.id)
        assert subscription is not None
        assert subscription.tier == PlanTier.starter
        assert subscription.message_usage_current_period == 1


async def test_redelivered_webhook_does_not_double_count(conversation):
    business, convo = conversation

    await load_context(_state(business.id, convo.thread_id, "hello", "wamid-usage-dup"))
    await load_context(_state(business.id, convo.thread_id, "hello", "wamid-usage-dup"))

    async with get_sessionmaker()() as session:
        subscription = await session.get(Subscription, business.id)
        assert subscription.message_usage_current_period == 1


async def test_usage_keeps_incrementing_past_cap(conversation):
    business, convo = conversation

    async with get_sessionmaker()() as session:
        subscription = await get_or_create_subscription(session, business)
        subscription.message_usage_current_period = 400  # already at the Starter cap
        await session.commit()

    await load_context(_state(business.id, convo.thread_id, "one more", "wamid-usage-overcap"))

    async with get_sessionmaker()() as session:
        subscription = await session.get(Subscription, business.id)
        assert subscription.message_usage_current_period == 401


async def test_lapsed_period_resets_usage(conversation):
    business, convo = conversation

    async with get_sessionmaker()() as session:
        subscription = await get_or_create_subscription(session, business)
        subscription.message_usage_current_period = 350
        subscription.period_end = datetime.now(UTC) - timedelta(days=1)
        await session.commit()

    await load_context(_state(business.id, convo.thread_id, "new period", "wamid-usage-rollover"))

    async with get_sessionmaker()() as session:
        subscription = await session.get(Subscription, business.id)
        assert subscription.message_usage_current_period == 1
        assert subscription.period_end > datetime.now(UTC)
