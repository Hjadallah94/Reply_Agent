from reply_agent.graph.risk_rules import (
    blocking_reason,
    evaluate_capability_gap,
    evaluate_risk_gate,
    order_context_found,
)


def make_intent(label="other", confidence=0.9, sentiment="neutral"):
    return {"label": label, "confidence": confidence, "sentiment": sentiment}


def test_price_negotiation_is_risk():
    assert evaluate_risk_gate(make_intent(label="price_negotiation")) is not None


def test_refund_or_complaint_is_risk():
    assert evaluate_risk_gate(make_intent(label="refund_or_complaint")) is not None


def test_competitor_mention_is_risk():
    assert evaluate_risk_gate(make_intent(label="competitor_mention")) is not None


def test_legal_threat_is_risk():
    assert evaluate_risk_gate(make_intent(label="legal_threat")) is not None


def test_ordinary_faq_is_not_risk():
    assert evaluate_risk_gate(make_intent(label="product_availability_price")) is None


def test_strong_negative_sentiment_is_risk_even_without_risk_label():
    intent = make_intent(label="other", confidence=0.8, sentiment="negative")
    assert evaluate_risk_gate(intent) is not None


def test_mild_negative_sentiment_below_threshold_is_not_risk():
    intent = make_intent(label="other", confidence=0.3, sentiment="negative")
    assert evaluate_risk_gate(intent) is None


def test_negative_sentiment_with_ordinary_label_gives_sentiment_reason():
    reason = evaluate_risk_gate(
        make_intent(label="policy_question", confidence=0.9, sentiment="negative")
    )
    assert reason is not None
    assert "sentiment" in reason.lower()


def test_order_status_is_a_capability_gap_not_a_risk():
    assert evaluate_risk_gate(make_intent(label="order_status")) is None
    assert evaluate_capability_gap(make_intent(label="order_status")) is not None


def test_ordinary_faq_has_no_capability_gap():
    assert evaluate_capability_gap(make_intent(label="product_availability_price")) is None


def test_blocking_reason_combines_risk_and_capability_gap():
    assert blocking_reason(make_intent(label="legal_threat")) is not None
    assert blocking_reason(make_intent(label="order_status")) is not None
    assert blocking_reason(make_intent(label="product_availability_price")) is None


def test_order_status_capability_gap_resolves_when_order_found():
    intent = make_intent(label="order_status")
    assert evaluate_capability_gap(intent, order_found=False) is not None
    assert evaluate_capability_gap(intent, order_found=True) is None
    assert blocking_reason(intent, order_found=True) is None


def test_order_found_does_not_bypass_other_risk_categories():
    # order_found should never accidentally waive a real risk category (e.g. a customer who
    # is both asking about an order AND negotiating a discount in the same classified intent).
    intent = make_intent(label="price_negotiation")
    assert blocking_reason(intent, order_found=True) is not None


def test_order_context_found_detects_order_prefixed_sources():
    assert order_context_found([{"source": "order:abc-123", "snippet": "...", "score": 1.0}])
    assert not order_context_found([{"source": "faq-doc-id", "snippet": "...", "score": 0.8}])
    assert not order_context_found([])
