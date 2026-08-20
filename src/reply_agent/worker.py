"""RQ worker entrypoint. RQ calls job functions synchronously, so process_inbound_message
wraps the actual async pipeline with asyncio.run() — everything below it (DB, Anthropic,
LangGraph) is async throughout, matching the FastAPI webhook side.

Run with: uv run rq worker inbound_messages
(or: uv run python -m reply_agent.worker for a quick local run)
"""

import asyncio
import logging

from reply_agent.db.models import ChannelType
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.context_resolution import (
    find_business_by_whatsapp_phone_number_id,
    get_or_create_conversation,
    get_or_create_customer,
)
from reply_agent.graph.graph import run_graph
from reply_agent.graph.state import GraphState

logger = logging.getLogger(__name__)


async def _process_inbound_message_async(payload: dict) -> None:
    async with get_sessionmaker()() as session:
        business = await find_business_by_whatsapp_phone_number_id(
            session, payload["phone_number_id"]
        )
        if business is None:
            logger.warning("No business found for phone_number_id=%s", payload["phone_number_id"])
            return

        customer = await get_or_create_customer(
            session, business.id, ChannelType.whatsapp, payload["from_wa_id"]
        )
        conversation = await get_or_create_conversation(
            session, business.id, ChannelType.whatsapp, customer
        )
        await session.commit()

        business_id, thread_id = str(business.id), conversation.thread_id

    initial_state: GraphState = {
        "business_id": business_id,
        "channel": "whatsapp",
        "customer_id": str(customer.id),
        "thread_id": thread_id,
        "message": {
            "text": payload["text"],
            "media_refs": [],
            "received_at": payload["timestamp"],
            "channel_message_id": payload["channel_message_id"],
        },
        "conversation_history": [],
        "customer_profile": {"past_orders": [], "preferences": {}, "prior_escalations": 0},
    }

    await run_graph(initial_state, thread_id=thread_id)


def process_inbound_message(payload: dict) -> None:
    asyncio.run(_process_inbound_message_async(payload))
