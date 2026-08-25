"""Shared helper for tests exercising routes gated by auth/dependencies.py (dashboard,
onboarding, knowledge/orders upload) — not itself a test file (no test_ prefix, so pytest
doesn't try to collect it).
"""

from reply_agent.auth.security import hash_password
from reply_agent.db.models import Business, PlanTier, User
from reply_agent.db.session import get_engine, get_sessionmaker
from reply_agent.db.tenant_session import get_app_engine

TEST_PASSWORD = "test-password-123"


async def dispose_engines() -> None:
    """FastAPI's TestClient runs the ASGI app on its own internal event loop (a separate
    thread's portal, not pytest's) — a connection pool created on one loop breaks the moment a
    later call tries to reuse it from the other. Two engines now (db/session.py's, for auth/
    scripts/the graph pipeline, and tenant_session.py's RLS-enforced one, for the dashboard/
    onboarding/upload routes) — dispose both at every loop transition, not just one.
    """
    await get_engine().dispose()
    await get_app_engine().dispose()


async def create_logged_in_business(client, name: str) -> Business:
    """Creates a Business + User in the DB and logs the given TestClient in as that user (the
    session cookie persists on the client for subsequent requests), returning the Business row.
    """
    async with get_sessionmaker()() as session:
        business = Business(name=name, plan_tier=PlanTier.starter)
        session.add(business)
        await session.flush()

        user = User(
            business_id=business.id,
            email=f"{business.id}@example.com",
            password_hash=hash_password(TEST_PASSWORD),
        )
        session.add(user)
        await session.commit()
        await session.refresh(business)
        email = user.email

    await dispose_engines()

    response = client.post(
        "/login", data={"email": email, "password": TEST_PASSWORD}, follow_redirects=False
    )
    assert response.status_code == 303, f"test login failed: {response.status_code}"

    await dispose_engines()

    return business
