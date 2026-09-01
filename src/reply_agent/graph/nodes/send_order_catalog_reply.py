"""Doc 3 roadmap (partner meeting 2026-09-01, order confirmation layer): "if the customer did
not accept the order, then the agent needs to provide the catalogue and make sure the customer
can see what they order." One-shot terminal node, same shape as send_away_reply.py — resolve
the Conversation, dispatch, write the outbound Message directly (bypassing update_memory, which
only fires on route == "send"), done.

Deterministic, not LLM-drafted: lists the real catalog verbatim (same KnowledgeDocument query
api/dashboard.py's catalog_list route already uses) rather than risking a paraphrase/omission
of what's actually for sale — the whole point of this step is letting the customer see their
real options, not a summary of them.
"""

import uuid

from sqlalchemy import select

from reply_agent.db.models import (
    Conversation,
    ConversationStatus,
    KnowledgeDocType,
    KnowledgeDocument,
    Message,
    MessageDirection,
)
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.nodes.send_reply import send_reply
from reply_agent.graph.state import GraphState

# Bilingual by default, same reasoning as send_away_reply.py's DEFAULT_AWAY_MESSAGE — the agent
# doesn't reliably know the customer's preferred language from a one-word "no" reply.
CATALOG_INTRO = (
    "ولا يهمك، هاي القائمة الكاملة تقدر تختار منها بالظبط اللي بدك ياه:\n"
    "No worries — here's our full menu so you can tell me exactly what you'd like:"
)


async def send_order_catalog_reply(state: GraphState) -> dict:
    business_id = uuid.UUID(state["business_id"])

    async with tenant_session(business_id) as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == state["thread_id"])
        )
        products = (
            await session.scalars(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.business_id == business_id,
                    KnowledgeDocument.type == KnowledgeDocType.product,
                )
                .order_by(KnowledgeDocument.structured_data["name"].astext)
            )
        ).all()

        catalog_text = "\n\n".join(doc.content for doc in products) or "(no products listed yet)"
        reply_text = f"{CATALOG_INTRO}\n\n{catalog_text}"

        # Reuses the same channel-dispatch code a real auto-send would go through, rather than
        # duplicating the WhatsApp/Instagram/Messenger match statement here.
        await send_reply(
            {
                "channel": state["channel"],
                "business_id": state["business_id"],
                "thread_id": state["thread_id"],
                "draft_reply": {"text": reply_text},
            }
        )

        # update_memory only logs an outbound message when route == "send" — this route stays
        # "order_declined", so this is the only record of the send.
        session.add(
            Message(
                conversation_id=conversation.id,
                direction=MessageDirection.outbound,
                text=reply_text,
                model_used="order-confirmation-catalog",
            )
        )
        conversation.status = ConversationStatus.auto

    return {
        "route": "order_declined",
        "draft_reply": {
            "text": reply_text,
            "cited_sources": [],
            "model_used": "order-confirmation-catalog",
        },
    }
