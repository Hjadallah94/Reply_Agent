"""Creates (or updates) the demo business row used by local testing and the eval harness,
and syncs its knowledge base from data/knowledge_base/example_business/.

Usage: uv run python scripts/seed_business.py
"""

import asyncio

from sqlalchemy import select

from reply_agent.auth.security import hash_password
from reply_agent.config import get_settings
from reply_agent.db.models import Business, PlanTier, User
from reply_agent.db.session import get_sessionmaker
from reply_agent.knowledge.loader import load_knowledge_base, sync_knowledge_base

BUSINESS_SLUG = "example_business"
BUSINESS_NAME = "Rose Abaya House"
DEMO_EMAIL = "demo@rose-abaya.example"
DEMO_PASSWORD = "demo-password-123"


async def main() -> None:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        business = await session.scalar(select(Business).where(Business.name == BUSINESS_NAME))
        if business is None:
            business = Business(name=BUSINESS_NAME, plan_tier=PlanTier.starter)
            session.add(business)
            await session.flush()

        business.channels_connected = {
            "whatsapp": {"phone_number_id": settings.whatsapp_phone_number_id}
        }

        # The dashboard needs a login (auth/dependencies.py) — create one for local testing if
        # this business doesn't have one yet. Real onboarded businesses sign up for their own
        # via /signup; this is only for the demo/dev business seeded here.
        existing_user = await session.scalar(select(User).where(User.business_id == business.id))
        if existing_user is None:
            session.add(
                User(
                    business_id=business.id,
                    email=DEMO_EMAIL,
                    password_hash=hash_password(DEMO_PASSWORD),
                )
            )

        await session.commit()
        business_id = business.id

        kb = load_knowledge_base(BUSINESS_SLUG)
        doc_count = await sync_knowledge_base(session, business_id, kb)
        await session.commit()

    print(f"Seeded business {business_id} ({BUSINESS_NAME}) with {doc_count} knowledge documents.")
    if existing_user is None:
        print(f"Dashboard login: {DEMO_EMAIL} / {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
