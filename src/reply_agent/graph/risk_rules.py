"""Risk categories that route to escalation regardless of downstream confidence (Doc 2 Section
2.4). This is a deterministic rule engine over classify_intent's structured output, not a
separate LLM call.

Doc 3 roadmap (partner meeting 2026-09-01): the four RISK_INTENT_LABELS and the negative-
sentiment threshold are now owner-configurable per business (Business.escalation_rules, wired
in via GraphState["escalation_rules"] — see graph/nodes/load_context.py). RISK_INTENT_LABELS/
SENSITIVITY_THRESHOLDS below are the *defaults* used when a business hasn't customized
anything, so every existing/unconfigured business keeps today's exact behavior. Deliberately
NOT configurable: NO_CAPABILITY_LABELS below — those escalate because the agent structurally
lacks grounded data, not because of risk tolerance, so toggling one off would let the agent
guess rather than express a genuine "I trust the agent with this topic" preference.
"""

from reply_agent.graph.state import Intent

RISK_INTENT_LABELS = {
    "price_negotiation",
    "refund_or_complaint",
    "competitor_mention",
    "legal_threat",
}

SENSITIVITY_THRESHOLDS = {"cautious": 0.4, "balanced": 0.6, "permissive": 0.8}
DEFAULT_SENSITIVITY = "balanced"

# The two reason shapes evaluate_risk_gate below produces — pulled out as constants so
# is_risk_category_reason (and evaluate_risk_gate itself) share one source of truth for the
# string shape, instead of a second module having to guess/duplicate it.
_RISK_CATEGORY_REASON_PREFIX = "Risk category: "
_NEGATIVE_SENTIMENT_REASON = "Strongly negative customer sentiment"

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


def evaluate_risk_gate(intent: Intent, escalation_rules: dict | None = None) -> str | None:
    """Returns a human-readable escalation reason if this intent should be risk-gated,
    else None. escalation_rules is the business's own Business.escalation_rules — None or
    missing keys fall back to RISK_INTENT_LABELS/DEFAULT_SENSITIVITY, today's exact behavior.
    """
    rules = escalation_rules or {}
    risk_categories = set(rules.get("risk_categories", RISK_INTENT_LABELS))
    threshold = SENSITIVITY_THRESHOLDS.get(
        rules.get("sensitivity", DEFAULT_SENSITIVITY), SENSITIVITY_THRESHOLDS[DEFAULT_SENSITIVITY]
    )
    if intent["label"] in risk_categories:
        return f"{_RISK_CATEGORY_REASON_PREFIX}{intent['label']}"
    if intent["sentiment"] == "negative" and intent["confidence"] >= threshold:
        return _NEGATIVE_SENTIMENT_REASON
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
    intent: Intent,
    *,
    order_found: bool = False,
    delivery_estimate_found: bool = False,
    escalation_rules: dict | None = None,
) -> str | None:
    """Combined check: any reason confidence_router must never choose 'send' for this intent."""
    return evaluate_risk_gate(intent, escalation_rules) or evaluate_capability_gap(
        intent, order_found=order_found, delivery_estimate_found=delivery_estimate_found
    )


def is_risk_category_reason(reason: str) -> bool:
    """True for an Escalation.reason produced by evaluate_risk_gate above, false for one
    produced by evaluate_capability_gap. Doc 3 roadmap (real gap found live, 12-message Petra
    Treasures conversation test, 2026-09-07) — graph/nodes/load_context.py uses this to decide
    which of a conversation's still-pending escalations represent a topic the owner explicitly
    wants to decide the outcome of, so generate_response.py can tell the model not to quietly
    resolve it in a later reply. Not surfaced for capability-gap escalations — the model
    structurally can't resolve those on its own regardless, a different problem already handled
    by generate_response.py's will_escalate_for_capability_gap.
    """
    return reason.startswith(_RISK_CATEGORY_REASON_PREFIX) or reason == _NEGATIVE_SENTIMENT_REASON


def order_context_found(retrieved_context: list) -> bool:
    """Whether retrieve_knowledge's order lookup (Doc 2 Section 2.6) actually found a match —
    those entries are tagged with a "order:" source prefix, see graph/nodes/retrieve_knowledge.py.
    """
    return any(c["source"].startswith("order:") for c in retrieved_context)
