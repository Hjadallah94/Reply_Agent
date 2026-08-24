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

# Not a risk category — these intents aren't sensitive, the agent just structurally can't
# answer them yet. An honest "I don't know" hedge is technically true but doesn't actually
# resolve the customer's need, so it shouldn't count as auto-resolved (Doc 1 Section 5).
# order_status: no order-lookup capability until Phase 2's spreadsheet/storefront integration
# (Doc 3 Phase 2). Revisit this once that integration exists.
NO_CAPABILITY_LABELS = {"order_status"}


def evaluate_risk_gate(intent: Intent) -> str | None:
    """Returns a human-readable escalation reason if this intent should be risk-gated,
    else None.
    """
    if intent["label"] in RISK_INTENT_LABELS:
        return f"Risk category: {intent['label']}"
    if intent["sentiment"] == "negative" and intent["confidence"] >= 0.6:
        return "Strongly negative customer sentiment"
    return None


def evaluate_capability_gap(intent: Intent) -> str | None:
    """Returns a human-readable escalation reason if the agent structurally lacks the data
    to answer this intent yet, else None.
    """
    if intent["label"] in NO_CAPABILITY_LABELS:
        return f"No {intent['label'].replace('_', ' ')} capability yet — needs a human answer"
    return None


def blocking_reason(intent: Intent) -> str | None:
    """Combined check: any reason confidence_router must never choose 'send' for this intent."""
    return evaluate_risk_gate(intent) or evaluate_capability_gap(intent)
