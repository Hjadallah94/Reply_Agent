"""Signup, login, logout, and cross-business isolation (api/auth.py, auth/dependencies.py).
Real DB.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from reply_agent.api.app import app
from reply_agent.auth.security import hash_password
from reply_agent.db.models import Business, User
from reply_agent.db.session import get_sessionmaker
from tests.auth_helpers import TEST_PASSWORD, create_logged_in_business, dispose_engines

SIGNUP_EMAIL = "owner@rose-abaya.example"
BUSINESS_NAME = "Rose Abaya Signup Test"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    # Every test above made at least one TestClient call — same cross-loop issue
    # create_logged_in_business's own dispose handles, needed again before this teardown.
    await dispose_engines()
    async with get_sessionmaker()() as session:
        await session.execute(delete(User).where(User.email == SIGNUP_EMAIL))
        await session.execute(delete(Business).where(Business.name == BUSINESS_NAME))
        await session.commit()


async def _user_for(business_name: str) -> User:
    async with get_sessionmaker()() as session:
        user = await session.scalar(
            select(User).join(Business).where(Business.name == business_name)
        )
    await dispose_engines()
    return user


async def test_signup_creates_business_and_logs_in(client):
    response = client.post(
        "/signup",
        data={
            "business_name": BUSINESS_NAME,
            "email": SIGNUP_EMAIL,
            "password": "a-strong-password",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/businesses/")
    assert response.headers["location"].endswith("/dashboard")

    await dispose_engines()

    async with get_sessionmaker()() as session:
        user = await session.scalar(
            select(User).where(User.email == SIGNUP_EMAIL).options(selectinload(User.business))
        )
        assert user is not None
        assert user.business.name == BUSINESS_NAME


async def test_signup_rejects_duplicate_email(client):
    client.post(
        "/signup",
        data={
            "business_name": BUSINESS_NAME,
            "email": SIGNUP_EMAIL,
            "password": "a-strong-password",
        },
        follow_redirects=False,
    )
    await dispose_engines()

    response = client.post(
        "/signup",
        data={
            "business_name": BUSINESS_NAME,
            "email": SIGNUP_EMAIL,
            "password": "a-different-password",
        },
    )
    assert response.status_code == 400
    assert "already registered" in response.text


async def test_signup_rejects_short_password(client):
    response = client.post(
        "/signup",
        data={"business_name": BUSINESS_NAME, "email": SIGNUP_EMAIL, "password": "short"},
    )
    assert response.status_code == 400
    assert "at least 8 characters" in response.text


async def test_login_succeeds_with_correct_credentials(client):
    await create_logged_in_business(client, BUSINESS_NAME)
    # create_logged_in_business already logs in as a side effect of creating the account;
    # log out and back in explicitly to test /login itself in isolation.
    client.post("/logout")
    await dispose_engines()

    user = await _user_for(BUSINESS_NAME)
    response = client.post(
        "/login",
        data={"email": user.email, "password": TEST_PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/businesses/{user.business_id}/dashboard"


async def test_login_rejects_wrong_password(client):
    await create_logged_in_business(client, BUSINESS_NAME)
    client.post("/logout")
    await dispose_engines()

    user = await _user_for(BUSINESS_NAME)
    response = client.post("/login", data={"email": user.email, "password": "wrong-password"})
    assert response.status_code == 400
    assert "Incorrect email or password" in response.text


async def test_login_rejects_unknown_email(client):
    response = client.post(
        "/login", data={"email": "nobody@example.com", "password": "whatever12345"}
    )
    assert response.status_code == 400
    assert "Incorrect email or password" in response.text


async def test_logout_clears_the_session(client):
    business = await create_logged_in_business(client, BUSINESS_NAME)

    client.post("/logout", follow_redirects=False)

    response = client.get(f"/businesses/{business.id}/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


async def test_user_cannot_view_a_different_business_dashboard(client):
    business_a = await create_logged_in_business(client, BUSINESS_NAME)

    async with get_sessionmaker()() as session:
        business_b = Business(name="Other Test Business")
        session.add(business_b)
        await session.flush()
        user_b = User(
            business_id=business_b.id,
            email="other-owner@example.com",
            password_hash=hash_password("other-password-123"),
        )
        session.add(user_b)
        await session.commit()
        email_b = user_b.email

    await dispose_engines()

    other_client = TestClient(app)
    other_client.post(
        "/login",
        data={"email": email_b, "password": "other-password-123"},
        follow_redirects=False,
    )
    await dispose_engines()

    # Business B's user tries to view Business A's dashboard.
    response = other_client.get(f"/businesses/{business_a.id}/dashboard")
    assert response.status_code == 404

    await dispose_engines()
    async with get_sessionmaker()() as session:
        await session.execute(delete(User).where(User.email == "other-owner@example.com"))
        await session.execute(delete(Business).where(Business.id == business_b.id))
        await session.commit()
