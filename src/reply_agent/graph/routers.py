"""Conditional-edge functions (Doc 2 Section 3.1): pure decision logic over state, no I/O."""

from typing import Literal

from reply_agent.graph.risk_rules import evaluate_risk_gate
from reply_agent.graph.state import GraphState

MAX_RETRIEVAL_ATTEMPTS = 2


def risk_gate(state: GraphState) -> Literal["risk", "normal"]:
    reason = evaluate_risk_gate(state["intent"])
    return "risk" if reason else "normal"


def confidence_router(state: GraphState) -> Literal["send", "retry", "escalate"]:
    self_check = state["self_check"]
    if self_check["passed"]:
        return "send"
    if self_check["needs_retry"] and state.get("retrieval_attempts", 0) < MAX_RETRIEVAL_ATTEMPTS:
        return "retry"
    return "escalate"
