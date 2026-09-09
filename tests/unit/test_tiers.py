"""billing/tiers.py — pure constants, no DB/API calls. Every dict must cover every PlanTier so
callers (api/dashboard.py, api/onboarding.py, signup/billing templates) never KeyError on a
tier nobody remembered to add a row for.
"""

from reply_agent.billing.tiers import (
    CATALOG_LIMIT,
    CHANNEL_LIMIT,
    MESSAGE_CAPS,
    OVERAGE_RATE_JOD,
    TIER_PRICE_JOD,
)
from reply_agent.db.models import PlanTier

ALL_TIERS = set(PlanTier)


def test_every_tier_has_a_message_cap():
    assert set(MESSAGE_CAPS) == ALL_TIERS


def test_every_tier_has_a_price():
    assert set(TIER_PRICE_JOD) == ALL_TIERS


def test_every_tier_has_an_overage_rate():
    assert set(OVERAGE_RATE_JOD) == ALL_TIERS


def test_every_tier_has_a_catalog_limit_entry():
    assert set(CATALOG_LIMIT) == ALL_TIERS


def test_pro_catalog_limit_is_unlimited():
    assert CATALOG_LIMIT[PlanTier.pro] is None


def test_starter_and_growth_catalog_limits_are_finite_and_increasing():
    assert CATALOG_LIMIT[PlanTier.starter] < CATALOG_LIMIT[PlanTier.growth]


def test_every_tier_has_a_channel_limit():
    assert set(CHANNEL_LIMIT) == ALL_TIERS


def test_channel_limits_are_strictly_increasing_by_tier():
    """Doc 3 roadmap (channel choice by tier, 2026-09-09) — a tier grants a *count* of channels,
    not specific ones (superseded the earlier fixed WhatsApp->+Messenger->+Instagram ladder), so
    what must hold is that a higher tier always gets to connect strictly more channels, not that
    it includes any particular one.
    """
    assert (
        CHANNEL_LIMIT[PlanTier.starter]
        < CHANNEL_LIMIT[PlanTier.growth]
        < CHANNEL_LIMIT[PlanTier.pro]
    )


def test_pro_channel_limit_covers_all_three_channels():
    assert CHANNEL_LIMIT[PlanTier.pro] == 3
