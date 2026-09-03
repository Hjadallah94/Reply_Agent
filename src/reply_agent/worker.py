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
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from reply_agent.channels.common import NormalizedInboundEvent
from reply_agent.db.models import (
    ChannelType,
    Conversation,
    Customer,
    Message,
    MessageDirection,
    Order,
    OrderConfirmationStatus,
)
from reply_agent.db.session import get_sessionmaker
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.context_resolution import (
    find_business_by_channel_key,
    get_or_create_conversation,
    get_or_create_customer,
)
from reply_agent.graph.graph import run_graph
from reply_agent.graph.nodes.send_reply import send_reply
from reply_agent.graph.state import GraphState

logger = logging.getLogger(__name__)

# Doc 3 roadmap (order confirmation follow-up) — bilingual by default, same reasoning as
# send_away_reply.py's DEFAULT_AWAY_MESSAGE: this fires with no live conversation turn to match
# the customer's language against.
DEFAULT_CONFIRMATION_NUDGE = (
    'ولسا ما اكدتلنا طلبك؟ إذا كل شي تمام معك بالطلب يلي حكينا عنه، اكتبلنا "أيوه" أو "تمام" '
    "وبنكمله، أو خبرنا شو بدك تغيّر.\n"
    'Just checking in — does the order we discussed look right to you? Reply "yes" to confirm, '
    "or let us know what to change."
)

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


async def _send_order_confirmation_nudge_async(order_id: str) -> None:
    """Doc 3 roadmap (order confirmation follow-up) — a delayed RQ job (queue/tasks.py's
    enqueue_order_confirmation_nudge), not a graph node: nothing here runs through LangGraph or
    touches GraphState, it operates directly on one Order row hours after the fact.
    """
    order_uuid = uuid.UUID(order_id)

    # Not tenant-scoped yet — business_id isn't known until this first, plain read (same
    # reasoning as _process_inbound_message_async's own initial business lookup above).
    async with get_sessionmaker()() as session:
        order = await session.get(Order, order_uuid)

    if order is None:
        logger.warning("Order confirmation nudge: order %s no longer exists", order_id)
        return
    if order.confirmation_status != OrderConfirmationStatus.pending:
        # Customer already replied (confirmed/declined/unclear) since this was scheduled —
        # nothing to nudge.
        return
    if order.confirmation_nudge_sent_at is not None:
        # Idempotency guard — confirmation_status deliberately stays "pending" after a nudge
        # (never auto-cancel/escalate), so it alone can't signal "already nudged."
        return

    async with tenant_session(order.business_id) as session:
        # Only WhatsApp customers are phone-identified (same convention as
        # retrieve_knowledge.py's order-status lookup) — Instagram/Messenger handles are
        # opaque IGSID/PSIDs, not phone numbers, so they'd never coincidentally match anyway.
        customer = await session.scalar(
            select(Customer).where(
                Customer.business_id == order.business_id,
                Customer.channel == ChannelType.whatsapp,
                Customer.channel_handle == order.customer_phone,
            )
        )
        if customer is None:
            logger.warning(
                "Order confirmation nudge: no WhatsApp customer found for order %s", order_id
            )
            return
        conversation = await session.scalar(
            select(Conversation).where(Conversation.customer_id == customer.id)
        )
        if conversation is None:
            logger.warning("Order confirmation nudge: no conversation found for order %s", order_id)
            return

        await send_reply(
            {
                "channel": conversation.channel.value,
                "business_id": str(order.business_id),
                "thread_id": conversation.thread_id,
                "draft_reply": {"text": DEFAULT_CONFIRMATION_NUDGE},
            }
        )

        session.add(
            Message(
                conversation_id=conversation.id,
                direction=MessageDirection.outbound,
                text=DEFAULT_CONFIRMATION_NUDGE,
                model_used="order-confirmation-nudge",
            )
        )

        # Re-fetch inside this session — `order` above was loaded in a different (non-tenant)
        # session and can't be mutated directly here.
        order_in_session = await session.get(Order, order_uuid)
        order_in_session.confirmation_nudge_sent_at = datetime.now(UTC)


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


def send_order_confirmation_nudge(order_id: str) -> None:
    """RQ job entrypoint for queue/tasks.py's enqueue_order_confirmation_nudge — reuses the
    same persistent worker-lifetime event loop as process_inbound_message, for the same reason
    (see the comment above _worker_loop): the DB engines are @lru_cache'd for the process's
    whole lifetime and stay bound to whichever loop first touched them.
    """
    _get_worker_loop().run_until_complete(_send_order_confirmation_nudge_async(order_id))
