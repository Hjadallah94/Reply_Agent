"""WhatsApp Embedded Signup callback (Doc 3 Phase 4). Real DB; Meta's own API calls are mocked
since this can't be exercised against Meta's real servers yet (no config_id / App Review
pending) — see onboarding/whatsapp_signup.py.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from reply_agent.api.app import app
from reply_agent.db.models import Business, PlanTier
from reply_agent.db.session import get_engine, get_sessionmaker
from reply_agent.onboarding.whatsapp_signup import EmbeddedSignupError

BUSINESS_NAME = "Onboarding Test Business"


@pytest.fixture
async def business():
    async with get_sessionmaker()() as session:
        b = Business(name=BUSINESS_NAME, plan_tier=PlanTier.starter)
        session.add(b)
        await session.commit()
        await session.refresh(b)
        yield b
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


async def test_signup_page_renders(business):
    client = TestClient(app)
    response = client.get("/onboarding/whatsapp", params={"business_id": str(business.id)})
    assert response.status_code == 200
    assert business.name in response.text


async def test_signup_page_404s_for_unknown_business():
    client = TestClient(app)
    response = client.get(
        "/onboarding/whatsapp", params={"business_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert response.status_code == 404


async def test_callback_saves_channels_connected(business):
    client = TestClient(app)
    with (
        patch(
            "reply_agent.api.onboarding.exchange_code_for_token",
            new=AsyncMock(return_value="business-token"),
        ),
        patch(
            "reply_agent.api.onboarding.subscribe_app_to_waba", new=AsyncMock()
        ) as mock_subscribe,
        patch("reply_agent.api.onboarding.register_phone_number", new=AsyncMock()) as mock_register,
    ):
        response = client.post(
            "/onboarding/whatsapp/callback",
            json={
                "business_id": str(business.id),
                "code": "the-code",
                "phone_number_id": "phone-123",
                "waba_id": "waba-456",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"connected": True}
    mock_subscribe.assert_called_once_with("waba-456", "business-token")
    mock_register.assert_called_once_with("phone-123", "business-token")

    await get_engine().dispose()

    async with get_sessionmaker()() as session:
        refreshed = await session.get(Business, business.id)
        assert refreshed.channels_connected["whatsapp"] == {
            "phone_number_id": "phone-123",
            "waba_id": "waba-456",
        }


async def test_callback_404s_for_unknown_business():
    client = TestClient(app)
    response = client.post(
        "/onboarding/whatsapp/callback",
        json={
            "business_id": "00000000-0000-0000-0000-000000000000",
            "code": "code",
            "phone_number_id": "p",
            "waba_id": "w",
        },
    )
    assert response.status_code == 404


async def test_callback_502s_when_meta_call_fails(business):
    client = TestClient(app)
    with patch(
        "reply_agent.api.onboarding.exchange_code_for_token",
        new=AsyncMock(side_effect=EmbeddedSignupError("boom")),
    ):
        response = client.post(
            "/onboarding/whatsapp/callback",
            json={
                "business_id": str(business.id),
                "code": "bad-code",
                "phone_number_id": "phone-123",
                "waba_id": "waba-456",
            },
        )
    assert response.status_code == 502


async def test_page_signup_page_renders(business):
    client = TestClient(app)
    response = client.get("/onboarding/page", params={"business_id": str(business.id)})
    assert response.status_code == 200
    assert business.name in response.text


async def test_page_callback_saves_messenger_and_instagram(business):
    client = TestClient(app)
    with (
        patch(
            "reply_agent.api.onboarding.exchange_code_for_token",
            new=AsyncMock(return_value="business-token"),
        ),
        patch(
            "reply_agent.api.onboarding.get_single_page_id",
            new=AsyncMock(return_value="page-123"),
        ),
        patch(
            "reply_agent.api.onboarding.get_linked_instagram_account_id",
            new=AsyncMock(return_value="ig-456"),
        ),
        patch(
            "reply_agent.api.onboarding.subscribe_page_to_app", new=AsyncMock()
        ) as mock_subscribe,
    ):
        response = client.post(
            "/onboarding/page/callback",
            json={"business_id": str(business.id), "code": "the-code"},
        )

    assert response.status_code == 200
    assert response.json() == {"connected": True, "instagram_connected": True}
    mock_subscribe.assert_called_once_with("page-123", "business-token")

    await get_engine().dispose()

    async with get_sessionmaker()() as session:
        refreshed = await session.get(Business, business.id)
        assert refreshed.channels_connected["messenger"] == {"page_id": "page-123"}
        assert refreshed.channels_connected["instagram"] == {"page_id": "page-123"}


async def test_page_callback_skips_instagram_when_not_linked(business):
    client = TestClient(app)
    with (
        patch(
            "reply_agent.api.onboarding.exchange_code_for_token",
            new=AsyncMock(return_value="business-token"),
        ),
        patch(
            "reply_agent.api.onboarding.get_single_page_id",
            new=AsyncMock(return_value="page-123"),
        ),
        patch(
            "reply_agent.api.onboarding.get_linked_instagram_account_id",
            new=AsyncMock(return_value=None),
        ),
        patch("reply_agent.api.onboarding.subscribe_page_to_app", new=AsyncMock()),
    ):
        response = client.post(
            "/onboarding/page/callback",
            json={"business_id": str(business.id), "code": "the-code"},
        )

    assert response.status_code == 200
    assert response.json() == {"connected": True, "instagram_connected": False}

    await get_engine().dispose()

    async with get_sessionmaker()() as session:
        refreshed = await session.get(Business, business.id)
        assert refreshed.channels_connected["messenger"] == {"page_id": "page-123"}
        assert "instagram" not in refreshed.channels_connected


async def test_page_callback_502s_when_multiple_pages_granted(business):
    client = TestClient(app)
    with (
        patch(
            "reply_agent.api.onboarding.exchange_code_for_token",
            new=AsyncMock(return_value="business-token"),
        ),
        patch(
            "reply_agent.api.onboarding.get_single_page_id",
            new=AsyncMock(side_effect=EmbeddedSignupError("2 Pages were granted")),
        ),
    ):
        response = client.post(
            "/onboarding/page/callback",
            json={"business_id": str(business.id), "code": "the-code"},
        )

    assert response.status_code == 502


async def test_page_callback_404s_for_unknown_business():
    client = TestClient(app)
    response = client.post(
        "/onboarding/page/callback",
        json={"business_id": "00000000-0000-0000-0000-000000000000", "code": "code"},
    )
    assert response.status_code == 404
