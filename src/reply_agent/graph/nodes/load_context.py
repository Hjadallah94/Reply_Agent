import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from reply_agent.billing.usage import record_customer_message
from reply_agent.db.models import (
    Business,
    Conversation,
    Customer,
    Escalation,
    Message,
    MessageDirection,
    Order,
    OrderConfirmationStatus,
)
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.nodes.estimate_delivery import AMMAN_TZ
from reply_agent.graph.state import ConversationTurn, GraphState

HISTORY_LIMIT = 10
# Doc 3 roadmap (order confirmation layer) — how long a customer has to reply to a
# confirmation-request before it's treated as abandoned rather than matched to whatever they
# say next (an unrelated message weeks later shouldn't get swallowed into an old order).
PENDING_CONFIRMATION_TTL = timedelta(hours=24)


async def load_context(state: GraphState) -> dict:
    async with tenant_session(uuid.UUID(state["business_id"])) as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == state["thread_id"])
        )
        if conversation is None:
            raise ValueError(f"No conversation for thread_id={state['thread_id']!r}")

        # Fetched unconditionally (not just for metering below) — is_away needs to reach state
        # on every run, not only a genuinely-new message (routers.py's load_context_router reads
        # it). customer is new (Doc 3 roadmap, order confirmation layer) — needed to look up a
        # pending Order by phone number below.
        business = await session.get(Business, conversation.business_id)
        customer = await session.get(Customer, uuid.UUID(state["customer_id"]))

        # Doc 3 roadmap (order confirmation layer) — the most recent still-unconfirmed
        # conversational order for this customer, if any and not stale. routers.py's
        # load_context_router sends this run straight to classify_confirmation_reply instead
        # of classify_intent when one is found.
        pending_order = await session.scalar(
            select(Order)
            .where(
                Order.business_id == conversation.business_id,
                Order.customer_phone == (customer.channel_handle if customer else ""),
                Order.confirmation_status == OrderConfirmationStatus.pending,
                Order.order_date >= datetime.now(AMMAN_TZ) - PENDING_CONFIRMATION_TTL,
            )
            .order_by(Order.order_date.desc())
            .limit(1)
        )

        # Query prior turns BEFORE inserting the current message — conversation_history must
        # exclude the message this run is currently processing (classify_intent/generate_response
        # append state["message"]["text"] separately; inserting first would duplicate it).
        prior_messages = (
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.desc())
                .limit(HISTORY_LIMIT)
            )
        ).all()

        # Idempotent insert: Meta retries undelivered webhooks, and the queue may redeliver too.
        insert_result = await session.execute(
            pg_insert(Message)
            .values(
                conversation_id=conversation.id,
                direction=MessageDirection.inbound,
                text=state["message"]["text"],
                channel_message_id=state["message"]["channel_message_id"],
            )
            .on_conflict_do_nothing(constraint="uq_messages_channel_message_id")
        )

        # Only meter genuinely new messages (Doc 5 Section 2 caps) — a redelivered webhook for
        # one already counted must not be charged twice.
        if insert_result.rowcount:
            await record_customer_message(session, business)

        prior_escalation_count = await session.scalar(
            select(func.count())
            .select_from(Escalation)
            .where(Escalation.conversation_id == conversation.id)
        )

    history: list[ConversationTurn] = [
        {
            "role": "customer" if m.direction == MessageDirection.inbound else "agent",
            "text": m.text,
            "created_at": m.created_at.isoformat(),
        }
        for m in reversed(prior_messages)
    ]

    return {
        "conversation_history": history,
        "customer_profile": {
            "past_orders": [],
            "preferences": {},
            "prior_escalations": prior_escalation_count or 0,
        },
        "business_is_away": business.is_away,
        "escalation_rules": business.escalation_rules,
        "pending_order": (
            {
                "id": str(pending_order.id),
                "order_reference": pending_order.order_reference,
                "delivery_window_promised": pending_order.delivery_window_promised,
            }
            if pending_order
            else None
        ),
    }
