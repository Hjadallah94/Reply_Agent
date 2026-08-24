"""Conditional-edge functions (Doc 2 Section 3.1): pure decision logic over state, no I/O.

The risk gate (Doc 2 Section 2.4) does NOT skip drafting — every message still flows through
retrieve_knowledge -> generate_response -> self_check so the owner always gets a grounded
drafted reply on escalation (Doc 1 Section 7). Risk categories only block confidence_router
from ever choosing "send"; they're evaluated here, at the same point self_check's result is
evaluated, rather than as a shortcut right after classify_intent. Capability gaps (risk_rules.py)
block "send" the same way, for a different reason: not risk, just missing data.
"""

from typing import Literal

from reply_agent.graph.risk_rules import blocking_reason
from reply_agent.graph.state import GraphState

MAX_RETRIEVAL_ATTEMPTS = 2


def blocks_auto_send(state: GraphState) -> bool:
    return blocking_reason(state["intent"]) is not None


def confidence_router(state: GraphState) -> Literal["send", "retry", "escalate"]:
    self_check = state["self_check"]

    if self_check["passed"] and not blocks_auto_send(state):
        return "send"
    if self_check["needs_retry"] and state.get("retrieval_attempts", 0) < MAX_RETRIEVAL_ATTEMPTS:
        return "retry"
    return "escalate"
