from reply_agent.billing.usage import usage_summary
from reply_agent.db.models import BillingStatus, PlanTier, Subscription


def _subscription(tier: PlanTier, used: int) -> Subscription:
    return Subscription(
        tier=tier,
        message_usage_current_period=used,
        billing_status=BillingStatus.trialing,
    )


def test_usage_summary_under_cap():
    summary = usage_summary(_subscription(PlanTier.starter, 100))
    assert summary == {"used": 100, "cap": 400, "over_cap": False, "remaining": 300}


def test_usage_summary_over_cap():
    summary = usage_summary(_subscription(PlanTier.starter, 450))
    assert summary["over_cap"] is True
    assert summary["remaining"] == 0


def test_usage_summary_at_cap_is_not_over():
    summary = usage_summary(_subscription(PlanTier.growth, 1500))
    assert summary["over_cap"] is False
    assert summary["remaining"] == 0
