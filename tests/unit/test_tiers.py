"""billing/tiers.py — pure constants, no DB/API calls. Every dict must cover every PlanTier so
callers (api/dashboard.py, api/onboarding.py, signup/billing templates) never KeyError on a
tier nobody remembered to add a row for.
"""

from reply_agent.billing.tiers import (
    CATALOG_LIMIT,
    CHANNELS_INCLUDED,
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


def test_every_tier_has_channels_included():
    assert set(CHANNELS_INCLUDED) == ALL_TIERS


def test_whatsapp_is_included_on_every_tier():
    assert all("whatsapp" in channels for channels in CHANNELS_INCLUDED.values())


def test_channel_access_is_strictly_additive_by_tier():
    """Doc 3 roadmap (real tier differentiation) — Growth's channels must be a superset of
    Starter's, and Pro's a superset of Growth's, or the "upgrade to unlock X" messaging in the
    dashboard/signup pages would be lying about what a higher tier actually gets you.
    """
    starter = set(CHANNELS_INCLUDED[PlanTier.starter])
    growth = set(CHANNELS_INCLUDED[PlanTier.growth])
    pro = set(CHANNELS_INCLUDED[PlanTier.pro])
    assert starter < growth < pro


def test_only_pro_includes_instagram():
    assert "instagram" not in CHANNELS_INCLUDED[PlanTier.starter]
    assert "instagram" not in CHANNELS_INCLUDED[PlanTier.growth]
    assert "instagram" in CHANNELS_INCLUDED[PlanTier.pro]
