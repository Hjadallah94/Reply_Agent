from reply_agent.graph.routers import MAX_RETRIEVAL_ATTEMPTS, confidence_router, risk_gate


def make_intent(label="other", confidence=0.9, sentiment="neutral"):
    return {"label": label, "confidence": confidence, "sentiment": sentiment}


def test_risk_gate_routes_risk_labels_to_risk():
    state = {"intent": make_intent(label="legal_threat")}
    assert risk_gate(state) == "risk"


def test_risk_gate_routes_ordinary_labels_to_normal():
    state = {"intent": make_intent(label="order_status")}
    assert risk_gate(state) == "normal"


def test_confidence_router_sends_on_pass():
    state = {"self_check": {"passed": True, "reason": "grounded", "needs_retry": False}}
    assert confidence_router(state) == "send"


def test_confidence_router_retries_when_under_attempt_limit():
    state = {
        "self_check": {"passed": False, "reason": "insufficient context", "needs_retry": True},
        "retrieval_attempts": MAX_RETRIEVAL_ATTEMPTS - 1,
    }
    assert confidence_router(state) == "retry"


def test_confidence_router_escalates_once_attempt_limit_reached():
    state = {
        "self_check": {"passed": False, "reason": "insufficient context", "needs_retry": True},
        "retrieval_attempts": MAX_RETRIEVAL_ATTEMPTS,
    }
    assert confidence_router(state) == "escalate"


def test_confidence_router_escalates_on_failed_check_without_retry_flag():
    state = {
        "self_check": {"passed": False, "reason": "ungrounded price claim", "needs_retry": False},
        "retrieval_attempts": 0,
    }
    assert confidence_router(state) == "escalate"
