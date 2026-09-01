"""notifications/push.py — real DB (Business/User/PushSubscription rows), the actual
pywebpush.webpush call mocked via _send_one (real per-call cost + needs a real subscription
otherwise, same reasoning as every other test this session mocking an external send).
"""

from unittest.mock import patch

import pytest
from pywebpush import WebPushException
from sqlalchemy import delete

from reply_agent.auth.security import hash_password
from reply_agent.db.models import Business, PlanTier, PushSubscription, User
from reply_agent.db.session import get_sessionmaker
from reply_agent.notifications.push import send_push_to_business

SEND_ONE_PATCH = "reply_agent.notifications.push._send_one"
SETTINGS_PATCH = "reply_agent.notifications.push.get_settings"


@pytest.fixture
async def business_with_user():
    async with get_sessionmaker()() as session:
        business = Business(name="Push Test Business", plan_tier=PlanTier.starter)
        session.add(business)
        await session.flush()

        user = User(
            business_id=business.id,
            email="push-test@example.com",
            password_hash=hash_password("irrelevant"),
        )
        session.add(user)
        await session.commit()
        await session.refresh(business)
        await session.refresh(user)
        yield business, user

        await session.execute(delete(Business).where(Business.id == business.id))
        await session.commit()


def _configured_settings(mock_settings):
    mock_settings.return_value.vapid_public_key = "pub"
    mock_settings.return_value.vapid_private_key = "priv"
    mock_settings.return_value.vapid_subject = "mailto:test@example.com"


async def test_no_op_when_vapid_not_configured(business_with_user):
    business, user = business_with_user
    async with get_sessionmaker()() as session:
        session.add(
            PushSubscription(
                business_id=business.id,
                user_id=user.id,
                endpoint="https://push.example.com/abc",
                p256dh_key="p256dh",
                auth_key="auth",
            )
        )
        await session.commit()

        with (
            patch(SETTINGS_PATCH) as mock_settings,
            patch(SEND_ONE_PATCH) as mock_send,
        ):
            mock_settings.return_value.vapid_public_key = ""
            mock_settings.return_value.vapid_private_key = ""
            await send_push_to_business(session, business.id, title="t", body="b", url="https://x")

    mock_send.assert_not_called()


async def test_no_op_when_no_subscriptions(business_with_user):
    business, _user = business_with_user
    async with get_sessionmaker()() as session:
        with (
            patch(SETTINGS_PATCH) as mock_settings,
            patch(SEND_ONE_PATCH) as mock_send,
        ):
            _configured_settings(mock_settings)
            await send_push_to_business(session, business.id, title="t", body="b", url="https://x")

    mock_send.assert_not_called()


async def test_sends_to_each_subscription(business_with_user):
    business, user = business_with_user
    async with get_sessionmaker()() as session:
        session.add_all(
            [
                PushSubscription(
                    business_id=business.id,
                    user_id=user.id,
                    endpoint="https://push.example.com/one",
                    p256dh_key="p1",
                    auth_key="a1",
                ),
                PushSubscription(
                    business_id=business.id,
                    user_id=user.id,
                    endpoint="https://push.example.com/two",
                    p256dh_key="p2",
                    auth_key="a2",
                ),
            ]
        )
        await session.commit()

        with (
            patch(SETTINGS_PATCH) as mock_settings,
            patch(SEND_ONE_PATCH) as mock_send,
        ):
            _configured_settings(mock_settings)
            await send_push_to_business(
                session, business.id, title="New order", body="details", url="https://x"
            )

    assert mock_send.call_count == 2


async def test_deletes_a_subscription_that_returns_410_gone(business_with_user):
    business, user = business_with_user
    async with get_sessionmaker()() as session:
        subscription = PushSubscription(
            business_id=business.id,
            user_id=user.id,
            endpoint="https://push.example.com/dead",
            p256dh_key="p1",
            auth_key="a1",
        )
        session.add(subscription)
        await session.commit()
        await session.refresh(subscription)
        subscription_id = subscription.id

        with (
            patch(SETTINGS_PATCH) as mock_settings,
            patch(
                SEND_ONE_PATCH, side_effect=WebPushException("gone", response=_FakeResponse(410))
            ),
        ):
            _configured_settings(mock_settings)
            await send_push_to_business(session, business.id, title="t", body="b", url="https://x")
        await session.commit()

    async with get_sessionmaker()() as session:
        assert await session.get(PushSubscription, subscription_id) is None


async def test_keeps_a_subscription_on_a_non_expiry_error(business_with_user):
    business, user = business_with_user
    async with get_sessionmaker()() as session:
        subscription = PushSubscription(
            business_id=business.id,
            user_id=user.id,
            endpoint="https://push.example.com/flaky",
            p256dh_key="p1",
            auth_key="a1",
        )
        session.add(subscription)
        await session.commit()
        await session.refresh(subscription)
        subscription_id = subscription.id

        with (
            patch(SETTINGS_PATCH) as mock_settings,
            patch(
                SEND_ONE_PATCH, side_effect=WebPushException("boom", response=_FakeResponse(500))
            ),
        ):
            _configured_settings(mock_settings)
            await send_push_to_business(session, business.id, title="t", body="b", url="https://x")
        await session.commit()

    async with get_sessionmaker()() as session:
        assert await session.get(PushSubscription, subscription_id) is not None


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
