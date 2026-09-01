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
lowest-priority slot in the router rather than pre-empting escalation.

is_away_router (Doc 3 roadmap, "I'm not available today") is different from all of the above:
it's the graph's second fan-out point (after self_check's), sitting right after load_context,
deliberately skipping classification/retrieval/generation/self-check entirely rather than
letting a node no-op internally (estimate_delivery's pattern) — every message gets the same
away-reply while away, including ones that would otherwise escalate, so there's nothing for
the rest of the pipeline to usefully do.
"""

from typing import Literal

from reply_agent.graph.risk_rules import blocking_reason, order_context_found
from reply_agent.graph.state import GraphState

MAX_RETRIEVAL_ATTEMPTS = 2


def is_away_router(state: GraphState) -> Literal["away", "continue"]:
    return "away" if state.get("business_is_away") else "continue"


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
    decline rather than a promise and keeps auto-sending unchanged.
    """
    intent = state.get("intent")
    delivery_estimate = state.get("delivery_estimate")
    return (
        intent is not None
        and intent["label"] == "place_order"
        and delivery_estimate is not None
        and delivery_estimate["same_day_eligible"]
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
