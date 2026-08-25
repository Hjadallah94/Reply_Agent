"""Pricing tiers as code (Doc 5 Section 2/4) — the source of truth for cap enforcement.
Keep in sync with 05_Pricing_Unit_Economics.md if the tiers change.
"""

from reply_agent.db.models import PlanTier

MESSAGE_CAPS: dict[PlanTier, int] = {
    PlanTier.starter: 400,
    PlanTier.growth: 1500,
    PlanTier.pro: 5000,
}

# JOD per customer message beyond the cap.
OVERAGE_RATE_JOD: dict[PlanTier, float] = {
    PlanTier.starter: 0.015,
    PlanTier.growth: 0.015,
    PlanTier.pro: 0.012,
}
