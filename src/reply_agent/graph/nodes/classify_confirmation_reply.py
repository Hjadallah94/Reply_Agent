"""Doc 3 roadmap (partner meeting 2026-09-01, order confirmation layer) — reached only when
load_context.py found a pending, unconfirmed conversational Order (routers.py's
load_context_router). A cheap Haiku call, same structured-output shape as self_check.py's
SelfCheckOutput, to decide whether the customer's latest reply actually confirms it.

Three-way, not binary (confirmed via AskUserQuestion): an ambiguous reply must never be guessed
either way — it goes to the owner via escalate_to_owner (reused as-is, see routers.py's
order_confirmation_router), same "never guess" philosophy as risk_rules.py's capability gaps.
"""

import uuid
from typing import Literal

from pydantic import BaseModel

from reply_agent.db.models import Order, OrderConfirmationStatus
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.state import GraphState
from reply_agent.llm.client import MODEL_HAIKU, get_anthropic_client

CLASSIFY_CONFIRMATION_SYSTEM_PROMPT = """You are reading a customer-service chat. The agent's \
last message summarized an order (items, price, delivery address, and delivery window) and \
asked the customer to confirm it's correct or say what to fix.

Decide what the customer's latest reply means:
- "confirmed": a clear yes/acceptance of the order as described ("yes", "ايوه", "تمام", "OK go \
ahead", a thumbs-up, etc.) — including a reply that only tweaks something minor (e.g. "yes but \
call me first") while still clearly accepting the order.
- "declined": a clear no, or a reply that describes a different/corrected order, or asks for \
something else entirely.
- "unclear": genuinely ambiguous — you cannot confidently tell whether they're confirming or \
not. Never guess; use this whenever in doubt.
"""

_DECISION_TO_STATUS = {
    "confirmed": OrderConfirmationStatus.confirmed,
    "declined": OrderConfirmationStatus.declined,
    "unclear": OrderConfirmationStatus.escalated,
}


class ConfirmationDecision(BaseModel):
    decision: Literal["confirmed", "declined", "unclear"]
    reason: str


async def _classify_reply(history_text: str, message_text: str) -> ConfirmationDecision:
    user_prompt = (
        f"Recent conversation:\n{history_text or '(no prior turns)'}\n\n"
        f"Customer's latest reply: {message_text}"
    )
    client = get_anthropic_client()
    response = await client.messages.parse(
        model=MODEL_HAIKU,
        max_tokens=200,
        system=CLASSIFY_CONFIRMATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        output_format=ConfirmationDecision,
    )
    return response.parsed_output


async def classify_confirmation_reply(state: GraphState) -> dict:
    pending = state["pending_order"]
    business_id = uuid.UUID(state["business_id"])

    history_text = "\n".join(
        f"{t['role']}: {t['text']}" for t in state.get("conversation_history", [])[-4:]
    )
    decision = (await _classify_reply(history_text, state["message"]["text"])).decision

    async with tenant_session(business_id) as session:
        order = await session.get(Order, uuid.UUID(pending["id"]))
        if order is not None:
            order.confirmation_status = _DECISION_TO_STATUS[decision]

    if decision == "confirmed":
        return {
            "order_confirmation_decision": "confirmed",
            # classify_intent was skipped on this run — reconstruct what downstream nodes
            # (generate_response, routers.py) need synthetically.
            "intent": {"label": "place_order", "confidence": 1.0, "sentiment": "neutral"},
            "delivery_estimate": {
                "same_day_eligible": pending["delivery_window_promised"] != "tomorrow",
                "estimated_window": pending["delivery_window_promised"],
                "reasoning": "Delivery estimate already confirmed with the customer.",
                "order_reference": pending["order_reference"],
            },
        }
    if decision == "declined":
        return {"order_confirmation_decision": "declined"}
    return {
        "order_confirmation_decision": "unclear",
        "escalation_override_reason": "Customer's reply to the order confirmation wasn't clear",
    }
