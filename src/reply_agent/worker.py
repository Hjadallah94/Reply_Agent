"""RQ worker entrypoint. RQ calls job functions synchronously, so process_inbound_message
wraps the actual async pipeline in an event loop — everything below it (DB, Anthropic,
LangGraph) is async throughout, matching the FastAPI webhook side.

One job function handles every channel — each webhook normalizes into the same
NormalizedInboundEvent shape (channels/common.py) before enqueueing, so nothing here needs to
know or care which app the message came from (Doc 1's "one brain, three channels").

Run with: uv run rq worker inbound_messages
(or: uv run python -m reply_agent.worker for a quick local run)
"""

import asyncio
import logging
import sys

from reply_agent.channels.common import NormalizedInboundEvent
from reply_agent.db.session import get_sessionmaker
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.context_resolution import (
    find_business_by_channel_key,
    get_or_create_conversation,
    get_or_create_customer,
)
from reply_agent.graph.graph import run_graph
from reply_agent.graph.state import GraphState

logger = logging.getLogger(__name__)

# psycopg's async driver (used by AsyncPostgresSaver, the LangGraph checkpointer) doesn't
# support Windows' default ProactorEventLoop — only SelectorEventLoop. Must be set before any
# event loop is created, so this runs at import time, not inside process_inbound_message.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def _process_inbound_message_async(payload: dict) -> None:
    event = NormalizedInboundEvent.model_validate(payload)

    # Which business owns this webhook's phone number/Page is exactly what we don't know yet —
    # this lookup searches across every business, so it can't be tenant-scoped (same reasoning
    # as auth/api/auth.py's login-by-email query). Everything after this point is scoped to the
    # one business it resolves to.
    async with get_sessionmaker()() as session:
        business = await find_business_by_channel_key(
            session, event.channel, event.business_lookup_key
        )
    if business is None:
        logger.warning(
            "No business found for channel=%s lookup_key=%s",
            event.channel.value,
            event.business_lookup_key,
        )
        return

    async with tenant_session(business.id) as session:
        customer = await get_or_create_customer(
            session, business.id, event.channel, event.customer_handle
        )
        conversation = await get_or_create_conversation(
            session, business.id, event.channel, customer
        )

    business_id, thread_id = str(business.id), conversation.thread_id

    initial_state: GraphState = {
        "business_id": business_id,
        "channel": event.channel.value,
        "customer_id": str(customer.id),
        "thread_id": thread_id,
        "message": {
            "text": event.text,
            "media_refs": [],
            "received_at": event.received_at,
            "channel_message_id": event.channel_message_id,
        },
        "conversation_history": [],
        "customer_profile": {"past_orders": [], "preferences": {}, "prior_escalations": 0},
    }

    await run_graph(initial_state, thread_id=thread_id)


# scripts/run_worker.py's SimpleWorker calls process_inbound_message synchronously, once per
# job, in the same process for its whole lifetime (chosen specifically because Windows can't
# fork). asyncio.run() creates and closes a fresh event loop every call — but db/session.py's
# get_engine() and db/tenant_session.py's get_app_engine() are @lru_cache'd for the process's
# whole lifetime, so their connection pools stay bound to whichever loop was active the first
# time they were used. The second job in a worker's life would try to reuse a pool bound to the
# first job's already-closed loop and crash ("Event loop is closed") — caught by running two
# real messages through one worker process in a row, not by any single-job test. One loop,
# reused for the worker's whole lifetime, keeps it aligned with the engines' own lifetime.
_worker_loop: asyncio.AbstractEventLoop | None = None


def _get_worker_loop() -> asyncio.AbstractEventLoop:
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    return _worker_loop


def process_inbound_message(payload: dict) -> None:
    _get_worker_loop().run_until_complete(_process_inbound_message_async(payload))
