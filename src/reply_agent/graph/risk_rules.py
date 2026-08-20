"""Hard-coded risk categories that always route to escalation regardless of downstream
confidence (Doc 2 Section 2.4). This is a deterministic rule engine over classify_intent's
structured output, not a separate LLM call.
"""

from reply_agent.graph.state import Intent

RISK_INTENT_LABELS = {
    "price_negotiation",
    "refund_or_complaint",
    "competitor_mention",
    "legal_threat",
}


def evaluate_risk_gate(intent: Intent) -> str | None:
    """Returns a human-readable escalation reason if this intent should be risk-gated,
    else None.
    """
    if intent["label"] in RISK_INTENT_LABELS:
        return f"Risk category: {intent['label']}"
    if intent["sentiment"] == "negative" and intent["confidence"] >= 0.6:
        return "Strongly negative customer sentiment"
    return None
