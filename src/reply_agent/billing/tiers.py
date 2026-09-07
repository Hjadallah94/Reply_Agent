"""Pricing tiers as code (Doc 5 Section 2/4) — the source of truth for cap enforcement.
Keep in sync with 05_Pricing_Unit_Economics.md if the tiers change.
"""

from reply_agent.db.models import PlanTier

MESSAGE_CAPS: dict[PlanTier, int] = {
    PlanTier.starter: 400,
    PlanTier.growth: 1500,
    PlanTier.pro: 5000,
}

# Doc 3 roadmap (Phase 4, manual/CliQ-style billing) — monthly subscription price, JOD.
TIER_PRICE_JOD: dict[PlanTier, float] = {
    PlanTier.starter: 10,
    PlanTier.growth: 25,
    PlanTier.pro: 45,
}

# JOD per customer message beyond the cap.
OVERAGE_RATE_JOD: dict[PlanTier, float] = {
    PlanTier.starter: 0.015,
    PlanTier.growth: 0.015,
    PlanTier.pro: 0.012,
}

# Doc 3 roadmap (real tier differentiation, 2026-09-07) — max products a business can list.
# None = unlimited. Proposed defaults, not derived from real usage data yet — adjust once real
# catalogs give a sense of what's actually needed. Enforced in api/dashboard.py's
# create_product_route; deliberately not retroactive (an existing business already over a newly
# -introduced cap keeps its existing products — only new creates are blocked), same convention
# as every other billing change in this codebase never touching existing data.
CATALOG_LIMIT: dict[PlanTier, int | None] = {
    PlanTier.starter: 20,
    PlanTier.growth: 100,
    PlanTier.pro: None,
}

# Doc 3 roadmap (real tier differentiation, 2026-09-07) — which channels a tier can connect.
# The source of truth api/onboarding.py's page_signup_callback, templates/dashboard.html's
# toolbar, and the signup/billing tier-comparison cards all read from, so they can never drift
# from each other. Messenger and Instagram are listed separately even though connecting a
# Facebook Page is one bundled flow that yields both together when the Page has Instagram linked
# — Growth unlocks the Page-connection flow but only activates the Messenger half; Pro
# additionally activates Instagram when present. See page_signup_callback's own docstring for
# the mechanics.
CHANNELS_INCLUDED: dict[PlanTier, list[str]] = {
    PlanTier.starter: ["whatsapp"],
    PlanTier.growth: ["whatsapp", "messenger"],
    PlanTier.pro: ["whatsapp", "messenger", "instagram"],
}


def tier_comparison_rows() -> list[dict]:
    """One row per PlanTier, every real feature difference in one place — signup.html's plan-
    first comparison and billing.html's change-plan page both render from this, so the two can
    never show a different story about what a tier actually gets you. Product photos are the one
    feature gate that isn't its own dict (billing/tiers.py's CATALOG_LIMIT/CHANNELS_INCLUDED are;
    api/dashboard.py's _save_product_image checks PlanTier.pro directly) — expressed the same way
    here for display purposes only.
    """
    return [
        {
            "value": tier.value,
            "label": tier.value.capitalize(),
            "price_jod": TIER_PRICE_JOD[tier],
            "message_cap": MESSAGE_CAPS[tier],
            "catalog_limit": CATALOG_LIMIT[tier],
            "channels": CHANNELS_INCLUDED[tier],
            "photos_included": tier == PlanTier.pro,
        }
        for tier in PlanTier
    ]
