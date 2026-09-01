"""Conditional-edge functions (Doc 2 Section 3.1): pure decision logic over state, no I/O.

The risk gate (Doc 2 Section 2.4) does NOT skip drafting — every message still flows through
retrieve_knowledge -> generate_response -> self_check so the owner always gets a grounded
drafted reply on escalation (Doc 1 Section 7). Risk categories only block confidence_router
from ever choosing "send"; they're evaluated here, at the same point self_check's result is
evaluated, rather than as a shortcut right after classify_intent. Capability gaps (risk_rules.py)
block "send" the same way, for a different reason: not risk, just missing data.

Owner approval (Doc 2 Section 9.2) is a third, distinct reason to not auto-send, evaluated only
once the draft has already passed self_check and cleared blocks_auto_send — a same-day delivery
commitment is a real, well-grounded answer, not an uncertain or ungrounded one, so it takes the
lowest-priority slot in the router rather than pre-empting escalation. Doc 3 roadmap (order
confirmation layer): it now also requires the customer to have actually confirmed the order
first (order_confirmation_decision == "confirmed") — a mere confirmation-request draft should
never need the owner's sign-off, only an order the customer has already agreed to.

load_context_router (Doc 3 roadmap) is different from all of the above: it's the graph's second
fan-out point (after self_check's), sitting right after load_context, deliberately skipping
classification/retrieval/generation/self-check entirely rather than letting a node no-op
internally (estimate_delivery's pattern). Three-way, in priority order:
1. away ("I'm not available today") — every message gets the same away-reply while away,
   including ones that would otherwise escalate or continue a pending order confirmation, so
   there's nothing for the rest of the pipeline to usefully do.
2. pending_confirmation (order confirmation layer) — the customer has an unconfirmed order
   waiting on their reply; skip straight to classifying that reply rather than running
   classify_intent on what's likely just "yes"/"no" text.
3. continue — the normal path, unchanged.

order_confirmation_router (Doc 3 roadmap) is the graph's third fan-out point, right after
classify_confirmation_reply: confirmed jumps straight into generate_response (skipping
classify_intent/estimate_delivery/retrieve_knowledge entirely — everything needed is already
known), declined goes to the new send_order_catalog_reply terminal node, and unclear goes
straight to the existing escalate_to_owner node (reused as-is; never guess when the agent isn't
sure the customer actually confirmed).
"""

from typing import Literal

from reply_agent.graph.risk_rules import blocking_reason, order_context_found
from reply_agent.graph.state import GraphState

MAX_RETRIEVAL_ATTEMPTS = 2


def load_context_router(state: GraphState) -> Literal["away", "pending_confirmation", "continue"]:
    if state.get("business_is_away"):
        return "away"
    if state.get("pending_order") is not None:
        return "pending_confirmation"
    return "continue"


def order_confirmation_router(state: GraphState) -> Literal["confirmed", "declined", "unclear"]:
    return state.get("order_confirmation_decision", "unclear")


def blocks_auto_send(state: GraphState) -> bool:
    order_found = order_context_found(state.get("retrieved_context", []))
    delivery_estimate_found = state.get("delivery_estimate") is not None
    return (
        blocking_reason(
            state["intent"],
            order_found=order_found,
            delivery_estimate_found=delivery_estimate_found,
            escalation_rules=state.get("escalation_rules"),
        )
        is not None
    )


def needs_owner_approval(state: GraphState) -> bool:
    """A same-day delivery commitment specifically — not a next-day deferral, which is a
    decline rather than a promise and keeps auto-sending unchanged. Doc 3 roadmap (order
    confirmation layer): also requires the customer to have already confirmed the order — the
    first-pass confirmation-request draft must never need the owner's sign-off, only the
    order the customer has actually agreed to.
    """
    intent = state.get("intent")
    delivery_estimate = state.get("delivery_estimate")
    return (
        intent is not None
        and intent["label"] == "place_order"
        and delivery_estimate is not None
        and delivery_estimate["same_day_eligible"]
        and state.get("order_confirmation_decision") == "confirmed"
    )


def confidence_router(state: GraphState) -> Literal["send", "retry", "escalate", "approve"]:
    self_check = state["self_check"]

    if self_check["passed"] and not blocks_auto_send(state):
        if needs_owner_approval(state):
            return "approve"
        return "send"
    if self_check["needs_retry"] and state.get("retrieval_attempts", 0) < MAX_RETRIEVAL_ATTEMPTS:
        return "retry"
    return "escalate"
