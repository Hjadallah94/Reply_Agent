import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from reply_agent.db.models import Conversation, Message, MessageDirection, Order
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.state import GraphState
from reply_agent.queue.tasks import enqueue_order_confirmation_nudge


async def update_memory(state: GraphState) -> dict:
    draft = state.get("draft_reply")
    if draft is None or state.get("route") != "send":
        # Escalations already wrote their own record in escalate_to_owner; nothing sent yet.
        return {}

    intent = state.get("intent", {})
    business_id = uuid.UUID(state["business_id"])
    order_id_to_nudge: uuid.UUID | None = None

    async with tenant_session(business_id) as session:
        conversation = await session.scalar(
            select(Conversation).where(Conversation.thread_id == state["thread_id"])
        )
        session.add(
            Message(
                conversation_id=conversation.id,
                direction=MessageDirection.outbound,
                text=draft["text"],
                intent_label=intent.get("label"),
                model_used=draft["model_used"],
            )
        )

        # Doc 3 roadmap (order confirmation follow-up) — this send is a confirmation-request
        # draft, not a final answer (generate_response.py). Only reachable here, not at Order
        # creation time (estimate_delivery.py), because only now do we know self_check/
        # confidence_router actually let it through to the customer rather than escalating.
        delivery_estimate = state.get("delivery_estimate")
        if state.get("require_order_confirmation") and delivery_estimate:
            order_reference = delivery_estimate.get("order_reference")
            if order_reference:
                order = await session.scalar(
                    select(Order).where(
                        Order.business_id == business_id,
                        Order.order_reference == order_reference,
                    )
                )
                if order is not None:
                    order.confirmation_sent_at = datetime.now(UTC)
                    order_id_to_nudge = order.id

    # Enqueued after the tenant_session block closes (so confirmation_sent_at is already
    # committed) — the job itself won't run for hours, so ordering here is about correctness
    # of what it'll see when it does, not timing.
    if order_id_to_nudge is not None:
        enqueue_order_confirmation_nudge(str(order_id_to_nudge))

    return {}
