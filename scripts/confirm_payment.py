"""Confirms a business's payment and activates their subscription — the one manual step
OptiGnosis takes once a CliQ transfer has actually been verified (Subscription docstring:
trialing -> payment_pending -> active, deliberately no self-serve "mark my own payment
confirmed" button, same reviewed-not-automatic precedent as CustomRule's approval flow).

Doc 3 roadmap (real gap found 2026-09-09, fixed 2026-09-14): before this script existed, that
manual step was a raw SQL UPDATE against Subscription.billing_status alone — Business.plan_tier
(the field every feature gate actually reads: CATALOG_LIMIT, CHANNEL_LIMIT, photos_included)
was never touched, so a business that paid for and was confirmed on a higher tier never actually
got the catalog/channel/photo access they paid for, only the higher message cap (which reads
Subscription.tier, not Business.plan_tier). This script does both updates in one atomic
transaction so the second half can't be forgotten.

Usage: uv run python scripts/confirm_payment.py <business_id>
       uv run python scripts/confirm_payment.py <business_id> --tier pro
       (--tier overrides what the business themselves requested — e.g. confirming a Custom-tier
       business, from the signup page's "Contact us" card, onto whichever real PlanTier their
       negotiated plan maps closest to.)
"""

import argparse
import asyncio
import uuid

from reply_agent.billing.usage import get_or_create_subscription
from reply_agent.db.models import BillingStatus, Business, PlanTier
from reply_agent.db.session import get_sessionmaker


async def confirm_payment(business_id: uuid.UUID, tier_override: PlanTier | None = None) -> None:
    async with get_sessionmaker()() as session:
        business = await session.get(Business, business_id)
        if business is None:
            raise ValueError(f"No business found for id={business_id}")

        subscription = await get_or_create_subscription(session, business)

        old_plan_tier, old_billing_status = business.plan_tier, subscription.billing_status
        new_tier = tier_override or subscription.tier

        subscription.tier = new_tier
        subscription.billing_status = BillingStatus.active
        business.plan_tier = new_tier

        await session.commit()

    print(f"Confirmed payment for {business.name} ({business_id}):")
    print(f"  plan_tier:      {old_plan_tier.value} -> {new_tier.value}")
    print(f"  billing_status: {old_billing_status.value} -> active")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("business_id", type=uuid.UUID)
    parser.add_argument(
        "--tier",
        choices=[t.value for t in PlanTier],
        default=None,
        help="Override the tier being confirmed (defaults to whatever the business requested).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    tier = PlanTier(args.tier) if args.tier else None
    asyncio.run(confirm_payment(args.business_id, tier))
