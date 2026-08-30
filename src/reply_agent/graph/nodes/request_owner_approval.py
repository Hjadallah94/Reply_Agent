"""Owner approval (Doc 2 Section 9.2) — distinct from escalation: the agent IS confident in
the drafted reply and its delivery estimate, but a same-day commitment is consequential enough
that it still needs the owner's sign-off before reaching the customer. Same one-shot shape as
escalate_to_owner.py: writes a row, notifies the owner, and the graph run ends there — the
owner's actual approve/reject decision is handled entirely by a separate dashboard route
(api/dashboard.py), never by re-entering the graph.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from reply_agent.channels.whatsapp.client import send_text_message
from reply_agent.config import get_settings
from reply_agent.db.models import ApprovalRequest, Conversation, ConversationStatus
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.context_resolution import get_whatsapp_phone_number_id
from reply_agent.graph.state import GraphState


async def request_owner_approval(state: GraphState) -> dict:
    draft_text = state["draft_reply"]["text"]
    delivery_estimate = state["delivery_estimate"]
    order_reference = delivery_estimate.get("order_reference")

    settings = get_settings()

    async with tenant_session(uuid.UUID(state["business_id"])) as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == state["thread_id"])
        )
        conversation.status = ConversationStatus.owner_handled

        session.add(
            ApprovalRequest(
                id=uuid.uuid4(),
                conversation_id=conversation.id,
                drafted_reply=draft_text,
                reasoning=delivery_estimate["reasoning"],
                order_reference=order_reference,
                notified_at=datetime.now(UTC),
            )
        )

        if settings.owner_notification_whatsapp_number:
            # Same convention as escalate_to_owner.py: notify from the business's own
            # connected number, no dashboard link included (the owner navigates there
            # themselves, consistent with how escalation notifications already work).
            phone_number_id = await get_whatsapp_phone_number_id(
                session, uuid.UUID(state["business_id"])
            )
            owner_message = (
                f"New order needs your approval — {delivery_estimate['estimated_window']} "
                "delivery.\n"
                f"Customer said: {state['message']['text']}\n\n"
                f"Drafted reply:\n{draft_text}"
            )
            await send_text_message(
                to=settings.owner_notification_whatsapp_number,
                text=owner_message,
                phone_number_id=phone_number_id,
            )

    return {
        "route": "approve",
        "approval": {
            "reasoning": delivery_estimate["reasoning"],
            "drafted_reply": draft_text,
            "order_reference": order_reference,
        },
    }
