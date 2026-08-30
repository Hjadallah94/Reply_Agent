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
# order_status: resolved when retrieve_knowledge finds a matching order (Doc 2 Section 2.6's
# spreadsheet sync) — see the order_found override below. Still a gap for every other business
# without order data synced, or for a customer/order retrieve_knowledge can't find a match for.
# place_order: resolved when estimate_delivery (Doc 2 Section 9.1) actually produces an estimate
# — still a gap when it can't (e.g. no delivery address given, or the business has no
# delivery_rules/address configured yet). Same reasoning as order_status: a hedge that doesn't
# actually answer the question shouldn't count as auto-resolved.
NO_CAPABILITY_LABELS = {"order_status", "place_order"}


def evaluate_risk_gate(intent: Intent) -> str | None:
    """Returns a human-readable escalation reason if this intent should be risk-gated,
    else None.
    """
    if intent["label"] in RISK_INTENT_LABELS:
        return f"Risk category: {intent['label']}"
    if intent["sentiment"] == "negative" and intent["confidence"] >= 0.6:
        return "Strongly negative customer sentiment"
    return None


def evaluate_capability_gap(
    intent: Intent, *, order_found: bool = False, delivery_estimate_found: bool = False
) -> str | None:
    """Returns a human-readable escalation reason if the agent structurally lacks the data
    to answer this intent, else None. order_found/delivery_estimate_found are set by
    confidence_router/escalate_to_owner from whether retrieve_knowledge's order lookup or
    estimate_delivery actually produced something for this conversation.
    """
    if intent["label"] not in NO_CAPABILITY_LABELS:
        return None
    if intent["label"] == "order_status" and order_found:
        return None
    if intent["label"] == "place_order" and delivery_estimate_found:
        return None
    return f"No {intent['label'].replace('_', ' ')} capability yet — needs a human answer"


def blocking_reason(
    intent: Intent, *, order_found: bool = False, delivery_estimate_found: bool = False
) -> str | None:
    """Combined check: any reason confidence_router must never choose 'send' for this intent."""
    return evaluate_risk_gate(intent) or evaluate_capability_gap(
        intent, order_found=order_found, delivery_estimate_found=delivery_estimate_found
    )


def order_context_found(retrieved_context: list) -> bool:
    """Whether retrieve_knowledge's order lookup (Doc 2 Section 2.6) actually found a match —
    those entries are tagged with a "order:" source prefix, see graph/nodes/retrieve_knowledge.py.
    """
    return any(c["source"].startswith("order:") for c in retrieved_context)
