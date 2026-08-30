"""Creates (or updates) a demo business row and syncs its knowledge base from
data/knowledge_base/<slug>/. Parameterized (Doc 3 Phase 6) so a second demo business — the
cookie shop used for delivery-estimation testing — can be seeded without duplicating this
script; defaults reproduce the original single-business behavior exactly.

Usage: uv run python scripts/seed_business.py
       uv run python scripts/seed_business.py --slug cookie_shop --name "Amman Cookie Co" \
           --email demo@cookie-shop.example --password demo-password-123 \
           --phone-number-id demo-cookie-shop-001 \
           --address "Jabal Amman, 3rd Circle, Amman" \
           --delivery-rules '{"cutoff_hour": 15, "min_lead_hours": 6}'
"""

import argparse
import asyncio
import json

from sqlalchemy import select

from reply_agent.auth.security import hash_password
from reply_agent.config import get_settings
from reply_agent.db.models import Business, PlanTier, User
from reply_agent.db.session import get_sessionmaker
from reply_agent.knowledge.loader import load_knowledge_base, sync_knowledge_base

DEFAULT_SLUG = "example_business"
DEFAULT_NAME = "Rose Abaya House"
DEFAULT_EMAIL = "demo@rose-abaya.example"
DEFAULT_PASSWORD = "demo-password-123"


async def seed_business(
    *,
    slug: str,
    name: str,
    email: str,
    password: str,
    phone_number_id: str | None = None,
    address: str | None = None,
    delivery_rules: dict | None = None,
) -> None:
    settings = get_settings()
    async with get_sessionmaker()() as session:
        business = await session.scalar(select(Business).where(Business.name == name))
        if business is None:
            business = Business(name=name, plan_tier=PlanTier.starter)
            session.add(business)
            await session.flush()

        business.channels_connected = {
            "whatsapp": {"phone_number_id": phone_number_id or settings.whatsapp_phone_number_id}
        }
        if address is not None:
            business.address = address
        if delivery_rules is not None:
            business.delivery_rules = delivery_rules

        # The dashboard needs a login (auth/dependencies.py) — create one for local testing if
        # this business doesn't have one yet. Real onboarded businesses sign up for their own
        # via /signup; this is only for the demo/dev businesses seeded here.
        existing_user = await session.scalar(select(User).where(User.business_id == business.id))
        if existing_user is None:
            session.add(
                User(business_id=business.id, email=email, password_hash=hash_password(password))
            )

        await session.commit()
        business_id = business.id

        kb = load_knowledge_base(slug)
        doc_count = await sync_knowledge_base(session, business_id, kb)
        await session.commit()

    print(f"Seeded business {business_id} ({name}) with {doc_count} knowledge documents.")
    if existing_user is None:
        print(f"Dashboard login: {email} / {password}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--phone-number-id", default=None)
    parser.add_argument("--address", default=None)
    parser.add_argument("--delivery-rules", default=None, help="JSON, e.g. '{\"cutoff_hour\": 15}'")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        seed_business(
            slug=args.slug,
            name=args.name,
            email=args.email,
            password=args.password,
            phone_number_id=args.phone_number_id,
            address=args.address,
            delivery_rules=json.loads(args.delivery_rules) if args.delivery_rules else None,
        )
    )
