"""Demo/App-Review helper only — NOT part of the product. Prints the conversation for the demo
customer number as a plain chat transcript, for on-screen use after scripts/demo_webhook_trigger.py
has run, in a screen recording for Meta App Review.

Usage: uv run python scripts/demo_show_reply.py
"""

import asyncio
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select

from reply_agent.db.models import Customer, Message
from reply_agent.db.session import get_sessionmaker

DEMO_CUSTOMER_NUMBER = "962790005555"


async def main() -> None:
    async with get_sessionmaker()() as session:
        customer = await session.scalar(
            select(Customer).where(Customer.channel_handle == DEMO_CUSTOMER_NUMBER)
        )
        if not customer:
            print("No demo conversation yet — run scripts/demo_webhook_trigger.py first.")
            return

        messages = (
            await session.scalars(
                select(Message)
                .join(Message.conversation)
                .where(Message.conversation.has(customer_id=customer.id))
                .order_by(Message.created_at)
            )
        ).all()

        print("=" * 50)
        for m in messages:
            speaker = "Customer" if str(m.direction) == "inbound" else "Reply Agent (AI)"
            print(f"{speaker}: {m.text}")
        print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
