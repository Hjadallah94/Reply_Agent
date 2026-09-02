"""Dashboard "Billing" page (Doc 3 roadmap, Phase 4: manual/CliQ-style billing) — real DB,
create_logged_in_business (tests/auth_helpers.py). No external calls to mock — this is a
DB-only + config-read feature, no payment gateway involved by design.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from reply_agent.api.app import app
from reply_agent.db.models import BillingStatus, Business, PlanTier, Subscription
from reply_agent.db.session import get_sessionmaker
from tests.auth_helpers import create_logged_in_business, dispose_engines

BUSINESS_NAME = "Billing Test Business"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
async def business(client):
    b = await create_logged_in_business(client, BUSINESS_NAME)
    yield b
    await dispose_engines()
    async with get_sessionmaker()() as session:
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


async def test_billing_page_shows_all_tiers_while_trialing(client, business):
    response = client.get(f"/businesses/{business.id}/dashboard/billing")
    assert response.status_code == 200
    assert "Starter" in response.text
    assert "Growth" in response.text
    assert "Pro" in response.text
    assert "10.0" in response.text or "10 " in response.text or ">10<" in response.text


async def test_request_plan_sets_tier_and_payment_pending(client, business):
    response = client.post(
        f"/businesses/{business.id}/dashboard/billing/request-plan",
        data={"tier": "growth"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/businesses/{business.id}/dashboard/billing"

    await dispose_engines()
    async with get_sessionmaker()() as session:
        subscription = await session.get(Subscription, business.id)
        assert subscription.tier == PlanTier.growth
        assert subscription.billing_status == BillingStatus.payment_pending


async def test_request_plan_rejects_invalid_tier(client, business):
    response = client.post(
        f"/businesses/{business.id}/dashboard/billing/request-plan",
        data={"tier": "enterprise"},
    )
    assert response.status_code == 400


async def test_billing_page_shows_instructions_when_payment_pending(client, business):
    client.post(
        f"/businesses/{business.id}/dashboard/billing/request-plan",
        data={"tier": "starter"},
        follow_redirects=False,
    )
    await dispose_engines()

    with patch("reply_agent.api.dashboard.get_settings") as mock_settings:
        mock_settings.return_value.payment_instructions = "CliQ alias: test-alias"
        mock_settings.return_value.vapid_public_key = ""
        response = client.get(f"/businesses/{business.id}/dashboard/billing")

    assert response.status_code == 200
    assert "CliQ alias: test-alias" in response.text
    assert str(business.id)[:8] in response.text


async def test_billing_page_shows_not_configured_fallback_when_instructions_empty(client, business):
    client.post(
        f"/businesses/{business.id}/dashboard/billing/request-plan",
        data={"tier": "starter"},
        follow_redirects=False,
    )
    await dispose_engines()

    with patch("reply_agent.api.dashboard.get_settings") as mock_settings:
        mock_settings.return_value.payment_instructions = ""
        mock_settings.return_value.vapid_public_key = ""
        response = client.get(f"/businesses/{business.id}/dashboard/billing")

    assert response.status_code == 200
    assert "set up yet" in response.text or "لسا ما انضبطت" in response.text


async def test_billing_page_shows_active_state(client, business):
    async with get_sessionmaker()() as session:
        session.add(
            Subscription(
                business_id=business.id,
                tier=PlanTier.pro,
                billing_status=BillingStatus.active,
            )
        )
        await session.commit()
    await dispose_engines()

    response = client.get(f"/businesses/{business.id}/dashboard/billing")
    assert response.status_code == 200
    assert "Pro" in response.text
    assert "active" in response.text.lower()


async def test_changing_plan_while_active_resets_to_payment_pending(client, business):
    async with get_sessionmaker()() as session:
        session.add(
            Subscription(
                business_id=business.id,
                tier=PlanTier.pro,
                billing_status=BillingStatus.active,
            )
        )
        await session.commit()
    await dispose_engines()

    client.post(
        f"/businesses/{business.id}/dashboard/billing/request-plan",
        data={"tier": "starter"},
        follow_redirects=False,
    )
    await dispose_engines()

    async with get_sessionmaker()() as session:
        subscription = await session.get(Subscription, business.id)
        assert subscription.tier == PlanTier.starter
        assert subscription.billing_status == BillingStatus.payment_pending


async def test_billing_routes_404_for_unowned_business(client, business):
    unowned = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/businesses/{unowned}/dashboard/billing").status_code == 404

    await dispose_engines()
    assert (
        client.post(
            f"/businesses/{unowned}/dashboard/billing/request-plan", data={"tier": "starter"}
        ).status_code
        == 404
    )
