""" "I'm not available today" (Doc 3 roadmap, partner meeting 2026-09-01) — a one-shot node,
same shape as escalate_to_owner.py: resolve the Conversation, dispatch, write the outbound
Message directly (bypassing update_memory, which only fires on route == "send"), done. No
owner notification of any kind — nothing for the owner to act on while deliberately away.
"""

import uuid

from sqlalchemy import select

from reply_agent.db.models import (
    Business,
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
)
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.nodes.send_reply import send_reply
from reply_agent.graph.state import GraphState

# Bilingual by default — the agent doesn't know the customer's preferred language up front
# (unlike the dashboard's own i18n.py, which is keyed on the owner's session language). The
# owner can override this from the dashboard with their own text in either/both languages.
DEFAULT_AWAY_MESSAGE = (
    "شكراً على تواصلكم! المتجر غير متاح اليوم، بس رح نرد عليك بأقرب وقت ممكن.\n"
    "Thanks for reaching out! We're not available today, but we'll get back to you as soon "
    "as we can."
)


async def send_away_reply(state: GraphState) -> dict:
    business_id = uuid.UUID(state["business_id"])

    async with tenant_session(business_id) as session:
        business = await session.get(Business, business_id)
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == state["thread_id"])
        )

        away_text = business.away_message or DEFAULT_AWAY_MESSAGE

        # Reuses the same channel-dispatch code a real auto-send would go through, rather than
        # duplicating the WhatsApp/Instagram/Messenger match statement here.
        await send_reply(
            {
                "channel": state["channel"],
                "business_id": state["business_id"],
                "thread_id": state["thread_id"],
                "draft_reply": {"text": away_text},
            }
        )

        # update_memory only logs an outbound message when route == "send" (graph/nodes/
        # update_memory.py) — this route stays "away", so this is the only record of the send.
        session.add(
            Message(
                conversation_id=conversation.id,
                direction=MessageDirection.outbound,
                text=away_text,
                model_used="away-mode",
            )
        )
        conversation.status = ConversationStatus.auto

    return {
        "route": "away",
        "draft_reply": {"text": away_text, "cited_sources": [], "model_used": "away-mode"},
    }
