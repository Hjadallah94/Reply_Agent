from reply_agent.graph.routers import (
    MAX_RETRIEVAL_ATTEMPTS,
    blocks_auto_send,
    confidence_router,
    needs_owner_approval,
)


def make_intent(label="other", confidence=0.9, sentiment="neutral"):
    return {"label": label, "confidence": confidence, "sentiment": sentiment}


def test_blocks_auto_send_true_for_risk_labels():
    assert blocks_auto_send({"intent": make_intent(label="legal_threat")}) is True


def test_blocks_auto_send_true_for_capability_gap_labels():
    assert blocks_auto_send({"intent": make_intent(label="order_status")}) is True


def test_blocks_auto_send_false_for_ordinary_labels():
    assert blocks_auto_send({"intent": make_intent(label="product_availability_price")}) is False


def test_confidence_router_sends_on_pass():
    state = {
        "intent": make_intent(label="product_availability_price"),
        "self_check": {"passed": True, "reason": "grounded", "needs_retry": False},
    }
    assert confidence_router(state) == "send"


def test_confidence_router_retries_when_under_attempt_limit():
    state = {
        "intent": make_intent(label="product_availability_price"),
        "self_check": {"passed": False, "reason": "insufficient context", "needs_retry": True},
        "retrieval_attempts": MAX_RETRIEVAL_ATTEMPTS - 1,
    }
    assert confidence_router(state) == "retry"


def test_confidence_router_escalates_once_attempt_limit_reached():
    state = {
        "intent": make_intent(label="product_availability_price"),
        "self_check": {"passed": False, "reason": "insufficient context", "needs_retry": True},
        "retrieval_attempts": MAX_RETRIEVAL_ATTEMPTS,
    }
    assert confidence_router(state) == "escalate"


def test_confidence_router_escalates_on_failed_check_without_retry_flag():
    state = {
        "intent": make_intent(label="product_availability_price"),
        "self_check": {"passed": False, "reason": "ungrounded price claim", "needs_retry": False},
        "retrieval_attempts": 0,
    }
    assert confidence_router(state) == "escalate"


def test_confidence_router_never_sends_a_risk_flagged_message_even_if_self_check_passes():
    """The core fix: risk gate must block send, but drafting/self_check still ran normally."""
    state = {
        "intent": make_intent(label="price_negotiation"),
        "self_check": {"passed": True, "reason": "grounded", "needs_retry": False},
        "retrieval_attempts": 1,
    }
    assert confidence_router(state) == "escalate"


def test_confidence_router_still_allows_retry_on_a_risk_flagged_message():
    state = {
        "intent": make_intent(label="refund_or_complaint"),
        "self_check": {"passed": False, "reason": "insufficient context", "needs_retry": True},
        "retrieval_attempts": 0,
    }
    assert confidence_router(state) == "retry"


def test_confidence_router_never_sends_order_status_even_when_self_check_passes():
    """order_status is a capability gap, not a risk category — same blocking effect either way."""
    state = {
        "intent": make_intent(label="order_status"),
        "self_check": {
            "passed": True,
            "reason": "honest hedge, well grounded",
            "needs_retry": False,
        },
        "retrieval_attempts": 0,
    }
    assert confidence_router(state) == "escalate"


def test_confidence_router_sends_order_status_when_an_order_was_found():
    """Doc 2 Section 2.6: once retrieve_knowledge finds a matching order, order_status is no
    longer a capability gap — normal self_check-based routing applies."""
    state = {
        "intent": make_intent(label="order_status"),
        "self_check": {
            "passed": True,
            "reason": "grounded in the order record",
            "needs_retry": False,
        },
        "retrieval_attempts": 0,
        "retrieved_context": [
            {"source": "order:abc-123", "snippet": "status=shipped", "score": 1.0}
        ],
    }
    assert confidence_router(state) == "send"


def test_blocks_auto_send_false_for_order_status_with_order_context():
    state = {
        "intent": make_intent(label="order_status"),
        "retrieved_context": [
            {"source": "order:abc-123", "snippet": "status=shipped", "score": 1.0}
        ],
    }
    assert blocks_auto_send(state) is False


def test_needs_owner_approval_true_for_same_day_eligible_place_order():
    state = {
        "intent": make_intent(label="place_order"),
        "delivery_estimate": {
            "same_day_eligible": True,
            "estimated_window": "3-4 hours",
            "reasoning": "quiet day",
        },
    }
    assert needs_owner_approval(state) is True


def test_needs_owner_approval_false_for_next_day_deferral():
    """A decline (same_day_eligible: False) auto-sends unchanged — it's not a commitment."""
    state = {
        "intent": make_intent(label="place_order"),
        "delivery_estimate": {
            "same_day_eligible": False,
            "estimated_window": "tomorrow",
            "reasoning": "past cutoff",
        },
    }
    assert needs_owner_approval(state) is False


def test_needs_owner_approval_false_when_delivery_estimate_missing():
    """A capability-gap place_order (no address/Maps failure) has delivery_estimate: None —
    that already routes to escalate via blocks_auto_send, not approve."""
    state = {"intent": make_intent(label="place_order"), "delivery_estimate": None}
    assert needs_owner_approval(state) is False


def test_confidence_router_routes_same_day_eligible_order_to_approve():
    state = {
        "intent": make_intent(label="place_order"),
        "self_check": {"passed": True, "reason": "grounded", "needs_retry": False},
        "retrieval_attempts": 0,
        "delivery_estimate": {
            "same_day_eligible": True,
            "estimated_window": "3-4 hours",
            "reasoning": "quiet day",
        },
    }
    assert confidence_router(state) == "approve"


def test_confidence_router_sends_next_day_deferral_unchanged():
    state = {
        "intent": make_intent(label="place_order"),
        "self_check": {"passed": True, "reason": "grounded", "needs_retry": False},
        "retrieval_attempts": 0,
        "delivery_estimate": {
            "same_day_eligible": False,
            "estimated_window": "tomorrow",
            "reasoning": "past cutoff",
        },
    }
    assert confidence_router(state) == "send"
