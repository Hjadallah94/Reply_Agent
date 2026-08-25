from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from reply_agent.billing.usage import record_customer_message
from reply_agent.db.models import Business, Conversation, Escalation, Message, MessageDirection
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.state import ConversationTurn, GraphState

HISTORY_LIMIT = 10


async def load_context(state: GraphState) -> dict:
    async with get_sessionmaker()() as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == state["thread_id"])
        )
        if conversation is None:
            raise ValueError(f"No conversation for thread_id={state['thread_id']!r}")

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
            business = await session.get(Business, conversation.business_id)
            await record_customer_message(session, business)

        prior_escalation_count = await session.scalar(
            select(func.count())
            .select_from(Escalation)
            .where(Escalation.conversation_id == conversation.id)
        )

        await session.commit()

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
    }
