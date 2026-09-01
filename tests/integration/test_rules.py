"""Dashboard "Rules & Autonomy" page (Doc 3 roadmap, partner meeting 2026-09-01) — real DB,
create_logged_in_business (tests/auth_helpers.py). No external calls to mock here (unlike
catalog.py's embed_documents) — these routes only touch Business.escalation_rules/
delivery_rules and the new CustomRule table.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from reply_agent.api.app import app
from reply_agent.db.models import Business, CustomRule, CustomRuleStatus
from reply_agent.db.session import get_sessionmaker
from tests.auth_helpers import create_logged_in_business, dispose_engines

BUSINESS_NAME = "Rules Test Business"


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


async def test_rules_page_renders_with_defaults(client, business):
    response = client.get(f"/businesses/{business.id}/dashboard/rules")
    assert response.status_code == 200
    assert "Rules &amp; Autonomy" in response.text or "Rules & Autonomy" in response.text
    # Every configurable category is checked by default (today's hardcoded behavior).
    assert response.text.count("checked") >= 4


async def test_save_autonomy_updates_escalation_rules(client, business):
    response = client.post(
        f"/businesses/{business.id}/dashboard/rules/autonomy",
        data={"sensitivity": "permissive", "refund_or_complaint": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/businesses/{business.id}/dashboard/rules"

    await dispose_engines()
    async with get_sessionmaker()() as session:
        refreshed = await session.get(Business, business.id)
        assert refreshed.escalation_rules["risk_categories"] == ["refund_or_complaint"]
        assert refreshed.escalation_rules["sensitivity"] == "permissive"


async def test_save_autonomy_with_no_categories_checked_saves_empty_list(client, business):
    client.post(
        f"/businesses/{business.id}/dashboard/rules/autonomy",
        data={"sensitivity": "balanced"},
        follow_redirects=False,
    )

    await dispose_engines()
    async with get_sessionmaker()() as session:
        refreshed = await session.get(Business, business.id)
        assert refreshed.escalation_rules["risk_categories"] == []


async def test_save_autonomy_rejects_invalid_sensitivity(client, business):
    response = client.post(
        f"/businesses/{business.id}/dashboard/rules/autonomy",
        data={"sensitivity": "extremely-cautious"},
    )
    assert response.status_code == 400


async def test_save_delivery_restrictions_parses_lines(client, business):
    response = client.post(
        f"/businesses/{business.id}/dashboard/rules/delivery-restrictions",
        data={"excluded_locations": "Zarqa\n\nAqaba\n  "},
        follow_redirects=False,
    )
    assert response.status_code == 303

    await dispose_engines()
    async with get_sessionmaker()() as session:
        refreshed = await session.get(Business, business.id)
        assert refreshed.delivery_rules["excluded_locations"] == ["Zarqa", "Aqaba"]


async def test_submit_custom_rule_creates_pending_row(client, business):
    response = client.post(
        f"/businesses/{business.id}/dashboard/rules/custom",
        data={"rule_text": "Always offer a 10% discount to repeat customers."},
        follow_redirects=False,
    )
    assert response.status_code == 303

    await dispose_engines()
    async with get_sessionmaker()() as session:
        rule = await session.scalar(select(CustomRule).where(CustomRule.business_id == business.id))
        assert rule is not None
        assert rule.rule_text == "Always offer a 10% discount to repeat customers."
        assert rule.status == CustomRuleStatus.pending


async def test_submit_custom_rule_rejects_blank_text(client, business):
    response = client.post(
        f"/businesses/{business.id}/dashboard/rules/custom",
        data={"rule_text": "   "},
    )
    assert response.status_code == 400


async def test_rules_page_lists_a_submitted_custom_rule(client, business):
    async with get_sessionmaker()() as session:
        session.add(
            CustomRule(
                id=uuid.uuid4(),
                business_id=business.id,
                rule_text="Never mention competitor prices.",
                status=CustomRuleStatus.pending,
            )
        )
        await session.commit()
    await dispose_engines()

    response = client.get(f"/businesses/{business.id}/dashboard/rules")
    assert response.status_code == 200
    assert "Never mention competitor prices." in response.text


UNOWNED_BUSINESS_ID = "00000000-0000-0000-0000-000000000000"


async def test_rules_page_404s_for_unowned_business(client, business):
    response = client.get(f"/businesses/{UNOWNED_BUSINESS_ID}/dashboard/rules")
    assert response.status_code == 404


async def test_save_autonomy_404s_for_unowned_business(client, business):
    response = client.post(f"/businesses/{UNOWNED_BUSINESS_ID}/dashboard/rules/autonomy", data={})
    assert response.status_code == 404


async def test_save_delivery_restrictions_404s_for_unowned_business(client, business):
    response = client.post(
        f"/businesses/{UNOWNED_BUSINESS_ID}/dashboard/rules/delivery-restrictions", data={}
    )
    assert response.status_code == 404


async def test_submit_custom_rule_404s_for_unowned_business(client, business):
    response = client.post(
        f"/businesses/{UNOWNED_BUSINESS_ID}/dashboard/rules/custom", data={"rule_text": "x"}
    )
    assert response.status_code == 404
