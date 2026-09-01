"""Owner approval (Doc 2 Section 9.2) — distinct from escalation: the agent IS confident in
the drafted reply and its delivery estimate, but a same-day commitment is consequential enough
that it still needs the owner's sign-off before reaching the customer. Same one-shot shape as
escalate_to_owner.py: writes a row, notifies the owner, and the graph run ends there — the
owner's actual approve/reject decision is handled entirely by a separate dashboard route
(api/dashboard.py), never by re-entering the graph.

Adaptive autonomy (Doc 2 Section 9.4): once a business's last N resolved approval_requests for a
given (business_id, estimated_window) pattern are all approved with sent_unchanged=True, a new
matching request auto-resolves here instead of going to the owner — same row shape, same audit
trail, just written as already-approved and dispatched immediately. This intentionally lives
inside this node (which already has DB I/O) rather than graph/routers.py's confidence_router,
which is documented as pure, no-I/O decision logic; needs_owner_approval() there is unchanged.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from reply_agent.channels.whatsapp.client import send_text_message
from reply_agent.config import get_settings
from reply_agent.db.models import (
    ApprovalRequest,
    ApprovalRequestStatus,
    Business,
    Conversation,
    ConversationStatus,
    Message,
    MessageDirection,
)
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.context_resolution import get_whatsapp_phone_number_id
from reply_agent.graph.nodes.send_reply import send_reply
from reply_agent.graph.state import GraphState
from reply_agent.notifications.push import send_push_to_business

DEFAULT_AUTO_APPROVE_THRESHOLD = 3
AUTO_APPROVAL_RESOLVED_BY = "system (adaptive autonomy)"


async def _matches_learned_pattern(
    session, business_id: uuid.UUID, estimated_window: str, threshold: int
) -> bool:
    """The last `threshold` resolved requests for this exact (business, window) pattern must
    all be approved-unchanged for the pattern to be considered learned. A reject or an edited
    approval sitting among the most recent `threshold` rows breaks this automatically — no
    separate reset bookkeeping needed, since this always re-checks the current tail of history.
    """
    recent = (
        await session.scalars(
            select(ApprovalRequest)
            .join(Conversation)
            .where(
                Conversation.business_id == business_id,
                ApprovalRequest.estimated_window == estimated_window,
                ApprovalRequest.status != ApprovalRequestStatus.pending,
            )
            .order_by(ApprovalRequest.created_at.desc())
            .limit(threshold)
        )
    ).all()
    return len(recent) >= threshold and all(
        a.status == ApprovalRequestStatus.approved and a.sent_unchanged for a in recent
    )


async def request_owner_approval(state: GraphState) -> dict:
    draft_text = state["draft_reply"]["text"]
    delivery_estimate = state["delivery_estimate"]
    order_reference = delivery_estimate.get("order_reference")
    estimated_window = delivery_estimate["estimated_window"]

    settings = get_settings()
    business_id = uuid.UUID(state["business_id"])

    async with tenant_session(business_id) as session:
        business = await session.get(Business, business_id)
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == state["thread_id"])
        )

        threshold = (business.delivery_rules or {}).get(
            "auto_approve_threshold", DEFAULT_AUTO_APPROVE_THRESHOLD
        )
        auto_approved = await _matches_learned_pattern(
            session, business_id, estimated_window, threshold
        )

        if auto_approved:
            # Reuses the same channel-dispatch code a human clicking Approve would go through
            # (api/dashboard.py's approve_approval) — same reasoning as escalate_to_owner.py's
            # own reuse note: no duplicating the WhatsApp/Instagram/Messenger match statement.
            await send_reply(
                {
                    "channel": state["channel"],
                    "business_id": state["business_id"],
                    "thread_id": state["thread_id"],
                    "draft_reply": {"text": draft_text},
                }
            )

            conversation.status = ConversationStatus.auto
            session.add(
                ApprovalRequest(
                    id=uuid.uuid4(),
                    conversation_id=conversation.id,
                    drafted_reply=draft_text,
                    reasoning=delivery_estimate["reasoning"],
                    order_reference=order_reference,
                    estimated_window=estimated_window,
                    sent_unchanged=True,
                    status=ApprovalRequestStatus.approved,
                    resolved_by=AUTO_APPROVAL_RESOLVED_BY,
                    resolution_time=datetime.now(UTC),
                )
            )
            # update_memory only logs an outbound message when route == "send" (graph/nodes/
            # update_memory.py) — this route stays "approve" below (see module docstring), so
            # this is the only record of the send, same as api/dashboard.py's approve_approval.
            session.add(
                Message(
                    conversation_id=conversation.id,
                    direction=MessageDirection.outbound,
                    text=draft_text,
                    model_used=state["draft_reply"]["model_used"],
                )
            )
        else:
            approval_id = uuid.uuid4()
            conversation.status = ConversationStatus.owner_handled

            session.add(
                ApprovalRequest(
                    id=approval_id,
                    conversation_id=conversation.id,
                    drafted_reply=draft_text,
                    reasoning=delivery_estimate["reasoning"],
                    order_reference=order_reference,
                    estimated_window=estimated_window,
                    notified_at=datetime.now(UTC),
                )
            )

            if settings.owner_notification_whatsapp_number:
                # Same convention as escalate_to_owner.py: notify from the business's own
                # connected number, no dashboard link included (the owner navigates there
                # themselves, consistent with how escalation notifications already work).
                phone_number_id = await get_whatsapp_phone_number_id(session, business_id)
                owner_message = (
                    f"New order needs your approval — {estimated_window} delivery.\n"
                    f"Customer said: {state['message']['text']}\n\n"
                    f"Drafted reply:\n{draft_text}"
                )
                await send_text_message(
                    to=settings.owner_notification_whatsapp_number,
                    text=owner_message,
                    phone_number_id=phone_number_id,
                )

            # Supplements, never replaces, the WhatsApp ping above — unlike it, this does carry
            # a deep link, since that's the whole point of a native push notification.
            push_url = (
                f"{settings.app_base_url}/businesses/{business_id}/dashboard/approvals/"
                f"{approval_id}"
                if settings.app_base_url
                else ""
            )
            await send_push_to_business(
                session,
                business_id,
                title="New order needs your approval",
                body=f"{estimated_window} delivery — {state['message']['text'][:120]}",
                url=push_url,
            )

    return {
        "route": "approve",
        "approval": {
            "reasoning": delivery_estimate["reasoning"],
            "drafted_reply": draft_text,
            "order_reference": order_reference,
        },
    }
