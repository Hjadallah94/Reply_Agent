"""Dashboard team seats (Doc 3 roadmap, 2026-09-15) — api/dashboard.py's team_page/add_teammate/
remove_teammate. Real DB, no external calls to mock (unlike catalog/onboarding tests, adding a
teammate is pure DB + password hashing, no LLM/Meta calls involved).
"""

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from reply_agent.api.app import app
from reply_agent.auth.security import hash_password
from reply_agent.billing.tiers import SEAT_LIMIT
from reply_agent.db.models import Business, PlanTier, User, UserRole
from reply_agent.db.session import get_sessionmaker
from tests.auth_helpers import TEST_PASSWORD, create_logged_in_business, dispose_engines

BUSINESS_NAME = "Team Seats Test Business"
PRO_BUSINESS_NAME = "Team Seats Test Business (Pro)"


def client() -> TestClient:
    return TestClient(app)


async def _cleanup(business_id) -> None:
    await dispose_engines()
    async with get_sessionmaker()() as session:
        await session.execute(delete(Business).where(Business.id == business_id))
        await session.commit()


async def _add_staff_user(business_id, email: str) -> User:
    # dispose before AND after — this raw session may be interleaved with TestClient calls on
    # either side (same cross-loop reasoning as create_logged_in_business's own two dispose
    # calls in tests/auth_helpers.py).
    await dispose_engines()
    async with get_sessionmaker()() as session:
        user = User(
            business_id=business_id,
            email=email,
            password_hash=hash_password(TEST_PASSWORD),
            role=UserRole.staff,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    await dispose_engines()
    return user


async def _owner_of(business_id) -> User:
    await dispose_engines()
    async with get_sessionmaker()() as session:
        owner = await session.scalar(select(User).where(User.business_id == business_id))
    await dispose_engines()
    return owner


async def test_team_page_shows_the_owner():
    c = client()
    business = await create_logged_in_business(c, BUSINESS_NAME)

    response = c.get(f"/businesses/{business.id}/dashboard/team")
    assert response.status_code == 200
    owner = await _owner_of(business.id)
    assert owner.email in response.text
    assert "Owner" in response.text

    await _cleanup(business.id)


async def test_owner_can_add_a_teammate_within_seat_limit():
    c = client()
    business = await create_logged_in_business(c, PRO_BUSINESS_NAME, plan_tier=PlanTier.pro)

    response = c.post(
        f"/businesses/{business.id}/dashboard/team/add",
        data={"email": "teammate@example.com", "password": "a-strong-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    await dispose_engines()
    async with get_sessionmaker()() as session:
        teammate = await session.scalar(select(User).where(User.email == "teammate@example.com"))
        assert teammate is not None
        assert teammate.role == UserRole.staff
        assert teammate.business_id == business.id

    await _cleanup(business.id)


async def test_starter_business_cannot_add_a_teammate_beyond_seat_limit():
    """SEAT_LIMIT[starter] is 1 — the owner themselves already fills that one seat."""
    c = client()
    business = await create_logged_in_business(c, BUSINESS_NAME)
    assert SEAT_LIMIT[PlanTier.starter] == 1

    response = c.post(
        f"/businesses/{business.id}/dashboard/team/add",
        data={"email": "teammate@example.com", "password": "a-strong-password"},
    )
    assert response.status_code == 400
    assert "seat" in response.text.lower()

    await dispose_engines()
    async with get_sessionmaker()() as session:
        assert (
            await session.scalar(select(User).where(User.email == "teammate@example.com")) is None
        )

    await _cleanup(business.id)


async def test_add_teammate_rejects_duplicate_email():
    c = client()
    business = await create_logged_in_business(c, PRO_BUSINESS_NAME, plan_tier=PlanTier.pro)
    owner = await _owner_of(business.id)

    response = c.post(
        f"/businesses/{business.id}/dashboard/team/add",
        data={"email": owner.email, "password": "a-strong-password"},
    )
    assert response.status_code == 400
    assert "already registered" in response.text.lower()

    await _cleanup(business.id)


async def test_add_teammate_rejects_short_password():
    c = client()
    business = await create_logged_in_business(c, PRO_BUSINESS_NAME, plan_tier=PlanTier.pro)

    response = c.post(
        f"/businesses/{business.id}/dashboard/team/add",
        data={"email": "teammate@example.com", "password": "short"},
    )
    assert response.status_code == 400

    await _cleanup(business.id)


async def test_staff_cannot_add_a_teammate():
    c = client()
    business = await create_logged_in_business(c, PRO_BUSINESS_NAME, plan_tier=PlanTier.pro)
    staff = await _add_staff_user(business.id, "staff@example.com")
    await dispose_engines()

    staff_client = client()
    staff_client.post(
        "/login", data={"email": staff.email, "password": TEST_PASSWORD}, follow_redirects=False
    )
    await dispose_engines()

    response = staff_client.post(
        f"/businesses/{business.id}/dashboard/team/add",
        data={"email": "another@example.com", "password": "a-strong-password"},
    )
    assert response.status_code == 403

    await _cleanup(business.id)


async def test_owner_can_remove_a_teammate():
    c = client()
    business = await create_logged_in_business(c, PRO_BUSINESS_NAME, plan_tier=PlanTier.pro)
    staff = await _add_staff_user(business.id, "staff@example.com")
    await dispose_engines()

    response = c.post(
        f"/businesses/{business.id}/dashboard/team/{staff.id}/remove", follow_redirects=False
    )
    assert response.status_code == 303

    await dispose_engines()
    async with get_sessionmaker()() as session:
        assert await session.get(User, staff.id) is None

    await _cleanup(business.id)


async def test_owner_cannot_remove_their_own_account():
    c = client()
    business = await create_logged_in_business(c, BUSINESS_NAME)
    owner = await _owner_of(business.id)

    response = c.post(f"/businesses/{business.id}/dashboard/team/{owner.id}/remove")
    assert response.status_code == 400

    await dispose_engines()
    async with get_sessionmaker()() as session:
        assert await session.get(User, owner.id) is not None

    await _cleanup(business.id)


async def test_staff_cannot_remove_a_teammate():
    c = client()
    business = await create_logged_in_business(c, PRO_BUSINESS_NAME, plan_tier=PlanTier.pro)
    staff = await _add_staff_user(business.id, "staff@example.com")
    owner = await _owner_of(business.id)
    await dispose_engines()

    staff_client = client()
    staff_client.post(
        "/login", data={"email": staff.email, "password": TEST_PASSWORD}, follow_redirects=False
    )
    await dispose_engines()

    response = staff_client.post(f"/businesses/{business.id}/dashboard/team/{owner.id}/remove")
    assert response.status_code == 403

    await _cleanup(business.id)


async def test_remove_teammate_404s_for_unknown_user():
    c = client()
    business = await create_logged_in_business(c, BUSINESS_NAME)

    response = c.post(
        f"/businesses/{business.id}/dashboard/team/00000000-0000-0000-0000-000000000000/remove"
    )
    assert response.status_code == 404

    await _cleanup(business.id)


async def test_remove_teammate_404s_for_a_user_on_a_different_business():
    c = client()
    business_a = await create_logged_in_business(c, BUSINESS_NAME)
    other_client = client()
    business_b = await create_logged_in_business(
        other_client, "Other Team Seats Business", plan_tier=PlanTier.pro
    )
    other_owner = await _owner_of(business_b.id)

    response = c.post(f"/businesses/{business_a.id}/dashboard/team/{other_owner.id}/remove")
    assert response.status_code == 404

    await _cleanup(business_a.id)
    await _cleanup(business_b.id)
