"""Creates (or updates) the demo business row used by local testing and the eval harness,
and syncs its knowledge base from data/knowledge_base/example_business/.

Usage: uv run python scripts/seed_business.py
"""

import asyncio

from sqlalchemy import select

from reply_agent.config import get_settings
from reply_agent.db.models import Business, PlanTier
from reply_agent.db.session import get_sessionmaker
from reply_agent.knowledge.loader import load_knowledge_base, sync_knowledge_base

BUSINESS_SLUG = "example_business"
BUSINESS_NAME = "Rose Abaya House"


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
        await session.commit()
        business_id = business.id

        kb = load_knowledge_base(BUSINESS_SLUG)
        doc_count = await sync_knowledge_base(session, business_id, kb)

    print(f"Seeded business {business_id} ({BUSINESS_NAME}) with {doc_count} knowledge documents.")


if __name__ == "__main__":
    asyncio.run(main())
