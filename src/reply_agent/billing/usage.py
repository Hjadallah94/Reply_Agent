"""Usage metering against the tier caps in Doc 5 Section 2. Soft cap by design — Doc 5 prices
overage per message rather than cutting a business off (Section 2: "Overage (beyond cap):
0.015 JOD/message"), so this tracks and surfaces usage; deciding to actually bill for overage
is Phase 4's separate payment-collection piece, not this one.

Billing periods are a fixed 30-day rolling window from first use, not anchored to a real payment
date — a simplification until real subscription billing (with its own billing-cycle dates) is
built.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from reply_agent.billing.tiers import MESSAGE_CAPS
from reply_agent.db.models import BillingStatus, Business, Subscription

PERIOD_LENGTH = timedelta(days=30)


async def get_or_create_subscription(session: AsyncSession, business: Business) -> Subscription:
    subscription = await session.get(Subscription, business.id)
    if subscription is not None:
        return subscription

    now = datetime.now(UTC)
    subscription = Subscription(
        business_id=business.id,
        tier=business.plan_tier,
        billing_status=BillingStatus.trialing,
        period_start=now,
        period_end=now + PERIOD_LENGTH,
    )
    session.add(subscription)
    await session.flush()
    return subscription


async def record_customer_message(session: AsyncSession, business: Business) -> Subscription:
    """Call once per genuine inbound customer message — not on webhook redeliveries of one
    already counted (callers should only invoke this after confirming the message is new).
    """
    subscription = await get_or_create_subscription(session, business)

    now = datetime.now(UTC)
    if subscription.period_end is not None and now >= subscription.period_end:
        subscription.message_usage_current_period = 0
        subscription.period_start = now
        subscription.period_end = now + PERIOD_LENGTH

    subscription.message_usage_current_period += 1
    return subscription


def usage_summary(subscription: Subscription) -> dict:
    cap = MESSAGE_CAPS[subscription.tier]
    used = subscription.message_usage_current_period
    return {
        "used": used,
        "cap": cap,
        "over_cap": used > cap,
        "remaining": max(cap - used, 0),
    }
