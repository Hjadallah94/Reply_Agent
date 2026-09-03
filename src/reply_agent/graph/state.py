"""Shared graph state (Doc 2, Section 4), adapted to concrete field types for this
implementation. One instance flows through every node; LangGraph's checkpointer persists
it after each node so a crash/restart resumes mid-conversation.
"""

from typing import Literal, NotRequired, TypedDict


class InboundMessage(TypedDict):
    text: str
    media_refs: list[str]
    received_at: str  # ISO 8601
    channel_message_id: str


class ConversationTurn(TypedDict):
    role: Literal["customer", "agent"]
    text: str
    created_at: str


class CustomerProfile(TypedDict):
    past_orders: list[str]
    preferences: dict
    prior_escalations: int


class Intent(TypedDict):
    label: str
    confidence: float
    sentiment: Literal["positive", "neutral", "negative"]
    risk_category: NotRequired[str | None]


class RetrievedChunk(TypedDict):
    source: str  # knowledge_documents.id as str
    snippet: str
    score: float


class DraftReply(TypedDict):
    text: str
    cited_sources: list[str]
    model_used: str


class SelfCheckResult(TypedDict):
    passed: bool
    reason: str
    needs_retry: bool


class EscalationRecord(TypedDict):
    reason: str
    drafted_reply: str
    notified_at: NotRequired[str | None]
    resolved_by: NotRequired[str | None]


class DeliveryEstimate(TypedDict):
    """graph/nodes/estimate_delivery.py's output (Doc 2 Section 9.1) — a live, computed
    answer, not a retrieved one. order_reference links to the Order row estimate_delivery
    writes (Doc 2 Section 9.2) — carried through so request_owner_approval can store it on
    the ApprovalRequest, letting a rejection update that specific Order later.
    """

    same_day_eligible: bool
    estimated_window: str
    reasoning: str
    order_reference: NotRequired[str | None]


class PendingOrder(TypedDict):
    """The most recent still-unconfirmed conversational Order for this customer (Doc 3 roadmap,
    order confirmation layer) — set by load_context.py, read by graph/routers.py's
    load_context_router and graph/nodes/classify_confirmation_reply.py.
    """

    id: str
    order_reference: str
    delivery_window_promised: str


class ApprovalRecord(TypedDict):
    """graph/nodes/request_owner_approval.py's output (Doc 2 Section 9.2) — distinct from
    EscalationRecord: this fires when the agent IS confident, not unsure, but a same-day
    delivery commitment is consequential enough to need the owner's sign-off first.
    """

    reasoning: str
    drafted_reply: str
    order_reference: NotRequired[str | None]
    notified_at: NotRequired[str | None]


class GraphState(TypedDict):
    business_id: str
    channel: Literal["whatsapp", "instagram", "messenger"]
    customer_id: str
    thread_id: str

    message: InboundMessage
    conversation_history: list[ConversationTurn]
    customer_profile: CustomerProfile

    # "I'm not available today" (Doc 3 roadmap) — set unconditionally by load_context.py, read
    # by graph/routers.py's load_context_router (pure, no DB call of its own).
    business_is_away: NotRequired[bool]
    # Business.escalation_rules (Doc 3 roadmap) — same load_context.py fetch, read by
    # risk_rules.py's evaluate_risk_gate via routers.py's blocks_auto_send (also pure).
    escalation_rules: NotRequired[dict]

    intent: NotRequired[Intent]
    retrieved_context: NotRequired[list[RetrievedChunk]]
    draft_reply: NotRequired[DraftReply]
    self_check: NotRequired[SelfCheckResult]
    route: NotRequired[Literal["send", "escalate", "retry", "approve", "away", "order_declined"]]
    escalation: NotRequired[EscalationRecord | None]
    delivery_estimate: NotRequired[DeliveryEstimate | None]
    approval: NotRequired[ApprovalRecord | None]

    # Doc 3 roadmap (order confirmation layer) — set by load_context.py/classify_confirmation_
    # reply.py, read by graph/routers.py (load_context_router, order_confirmation_router,
    # needs_owner_approval) and graph/nodes/escalate_to_owner.py.
    pending_order: NotRequired[PendingOrder | None]
    order_confirmation_decision: NotRequired[Literal["confirmed", "declined", "unclear"]]
    escalation_override_reason: NotRequired[str]
    # Doc 3 roadmap (order confirmation follow-up) — set by generate_response.py, read by
    # update_memory.py: this send (if it happens) is a confirmation-request draft, not a final
    # answer, so update_memory.py should stamp Order.confirmation_sent_at and schedule the
    # nudge job once it actually sends.
    require_order_confirmation: NotRequired[bool]

    retrieval_attempts: NotRequired[int]
