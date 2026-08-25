"""Shared helper for tests exercising routes gated by auth/dependencies.py (dashboard,
onboarding, knowledge/orders upload) — not itself a test file (no test_ prefix, so pytest
doesn't try to collect it).
"""

from reply_agent.auth.security import hash_password
from reply_agent.db.models import Business, PlanTier, User
from reply_agent.db.session import get_engine, get_sessionmaker

TEST_PASSWORD = "test-password-123"


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

    # TestClient.post runs the ASGI app on its own internal event loop (a separate thread's
    # portal, not pytest's) — the connection pool from the direct session access just above,
    # created on pytest's own loop, breaks the moment the login request tries to reuse it from
    # that other loop. Dispose before the call, not just after.
    await get_engine().dispose()

    response = client.post(
        "/login", data={"email": email, "password": TEST_PASSWORD}, follow_redirects=False
    )
    assert response.status_code == 303, f"test login failed: {response.status_code}"

    await get_engine().dispose()

    return business
