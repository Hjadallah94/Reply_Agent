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
    answer, not a retrieved one. No approval-related fields yet: that's Phase 6c, a later
    increment, not this one.
    """

    same_day_eligible: bool
    estimated_window: str
    reasoning: str


class GraphState(TypedDict):
    business_id: str
    channel: Literal["whatsapp", "instagram", "messenger"]
    customer_id: str
    thread_id: str

    message: InboundMessage
    conversation_history: list[ConversationTurn]
    customer_profile: CustomerProfile

    intent: NotRequired[Intent]
    retrieved_context: NotRequired[list[RetrievedChunk]]
    draft_reply: NotRequired[DraftReply]
    self_check: NotRequired[SelfCheckResult]
    route: NotRequired[Literal["send", "escalate", "retry"]]
    escalation: NotRequired[EscalationRecord | None]
    delivery_estimate: NotRequired[DeliveryEstimate | None]

    retrieval_attempts: NotRequired[int]
