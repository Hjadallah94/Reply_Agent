"""Escalation is a first-class feature (Doc 1 Section 7 / Doc 2 Section 2.5): the owner gets
a drafted, ready-to-approve reply plus a one-line reason, not a bare alert. By the time this
node runs, retrieve_knowledge -> generate_response -> self_check have always already run
(graph.py), so drafted_reply is populated here whenever the graph produced one at all — the
only way it's empty is if generate_response itself failed upstream.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from reply_agent.channels.whatsapp.client import send_text_message
from reply_agent.config import get_settings
from reply_agent.db.models import Conversation, ConversationStatus, Escalation
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.context_resolution import get_whatsapp_phone_number_id
from reply_agent.graph.risk_rules import blocking_reason, order_context_found
from reply_agent.graph.state import GraphState


def _escalation_reason(state: GraphState) -> str:
    # Prefer the risk/capability-gap reason when present — it's more actionable for the owner
    # than a self_check note, even if self_check happened to pass this particular draft.
    intent = state.get("intent")
    order_found = order_context_found(state.get("retrieved_context", []))
    reason = blocking_reason(intent, order_found=order_found) if intent else None
    if reason:
        return reason

    self_check = state.get("self_check")
    if self_check and not self_check["passed"]:
        return self_check["reason"]
    return "Escalated"


async def escalate_to_owner(state: GraphState) -> dict:
    draft_text = state.get("draft_reply", {}).get("text", "")
    reason = _escalation_reason(state)

    settings = get_settings()

    async with get_sessionmaker()() as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == state["thread_id"])
        )
        conversation.status = ConversationStatus.owner_handled

        session.add(
            Escalation(
                id=uuid.uuid4(),
                conversation_id=conversation.id,
                reason=reason,
                drafted_reply=draft_text or None,
                notified_at=datetime.now(UTC),
            )
        )

        if settings.owner_notification_whatsapp_number:
            # Notify from the same business's own number, not a global default (Doc 3 Phase 4:
            # self-serve means many onboarded businesses, each with their own connected number).
            phone_number_id = await get_whatsapp_phone_number_id(
                session, uuid.UUID(state["business_id"])
            )
            owner_message = (
                f"New escalation ({reason}).\n"
                f"Customer said: {state['message']['text']}\n\n"
                f"Drafted reply:\n{draft_text or '(no draft — reply from scratch)'}"
            )
            await send_text_message(
                to=settings.owner_notification_whatsapp_number,
                text=owner_message,
                phone_number_id=phone_number_id,
            )

        await session.commit()

    return {
        "route": "escalate",
        "escalation": {"reason": reason, "drafted_reply": draft_text},
    }
