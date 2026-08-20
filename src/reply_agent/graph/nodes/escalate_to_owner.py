"""Escalation is a first-class feature (Doc 1 Section 7 / Doc 2 Section 2.5): the owner gets
a drafted, ready-to-approve reply plus a one-line reason, not a bare alert.

Note a real tension between the two docs that this implementation does NOT resolve: Doc 1
Section 7 says the owner always gets "a ready-to-send drafted reply", but Doc 2's flow diagram
(Section 3.1) routes risk-flagged messages straight from classify_intent to escalate_to_owner,
bypassing generate_response entirely — so risk-gated escalations (discount requests,
complaints, etc.) reach this node with no draft (drafted_reply left None below), while only
self_check-triggered escalations carry one. Worth a deliberate decision before Phase 3 builds
the real draft-and-approve UI around this.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from reply_agent.channels.whatsapp.client import send_text_message
from reply_agent.config import get_settings
from reply_agent.db.models import Conversation, ConversationStatus, Escalation
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.state import GraphState


def _escalation_reason(state: GraphState) -> str:
    self_check = state.get("self_check")
    if self_check and not self_check["passed"]:
        return self_check["reason"]
    intent = state.get("intent")
    if intent:
        return f"Risk category: {intent['label']}"
    return "Escalated"


async def escalate_to_owner(state: GraphState) -> dict:
    draft_text = state.get("draft_reply", {}).get("text", "")
    reason = _escalation_reason(state)

    settings = get_settings()
    if settings.owner_notification_whatsapp_number:
        owner_message = (
            f"New escalation ({reason}).\n"
            f"Customer said: {state['message']['text']}\n\n"
            f"Drafted reply:\n{draft_text or '(no draft — reply from scratch)'}"
        )
        await send_text_message(to=settings.owner_notification_whatsapp_number, text=owner_message)

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
        await session.commit()

    return {
        "route": "escalate",
        "escalation": {"reason": reason, "drafted_reply": draft_text},
    }
