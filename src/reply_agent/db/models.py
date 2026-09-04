"""SQLAlchemy models for the data model in Doc 2, Section 5.

Tenant isolation (business_id on every tenant-scoped table) is enforced at the application
query layer, and at the database level too, via Postgres row-level security
(db/tenant_session.py, migrations/versions/325e6d70b285_*.py; README's "Row-level security"
section has the full picture) — both the web-facing API surface and the LangGraph pipeline
(worker.py, graph/nodes/*) go through it. Not covered: the LangGraph checkpointer's own tables
(memory/checkpointer.py) — a separate connection mechanism entirely, with no business_id column
to filter on; extending RLS there would be distinct, larger follow-up work.
"""

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Voyage's default embedding dimension for voyage-3.5 / voyage-3. Verify against Voyage's
# current docs if the embedding model changes (config.voyage_embedding_model).
EMBEDDING_DIM = 1024


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class ChannelType(enum.StrEnum):
    whatsapp = "whatsapp"
    instagram = "instagram"
    messenger = "messenger"


class PlanTier(enum.StrEnum):
    starter = "starter"
    growth = "growth"
    pro = "pro"


class KnowledgeDocType(enum.StrEnum):
    product = "product"
    policy = "policy"
    faq = "faq"
    brand_voice = "brand_voice"
    # Dashboard-only (Doc 3 Phase 6.5) — never part of a spreadsheet upload/KnowledgeBase, see
    # knowledge/catalog.py. active_from/active_until below only ever get set on this type.
    promotion = "promotion"


class ConversationStatus(enum.StrEnum):
    auto = "auto"
    owner_handled = "owner_handled"
    closed = "closed"


class MessageDirection(enum.StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class EscalationStatus(enum.StrEnum):
    pending = "pending"
    resolved = "resolved"
    timed_out = "timed_out"


class ApprovalRequestStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class CustomRuleStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class OrderConfirmationStatus(enum.StrEnum):
    """Doc 3 roadmap (partner meeting 2026-09-01, order confirmation layer) — only ever set for
    orders created live through a conversation (graph/nodes/estimate_delivery.py); stays NULL
    for spreadsheet-synced orders (orders/sync.py), which never go through this round-trip.
    `escalated` is the "customer's confirmation reply was ambiguous" case — the owner takes it
    from there via the normal escalation flow, so this Order's own state machine stops here.
    """

    pending = "pending"
    confirmed = "confirmed"
    declined = "declined"
    escalated = "escalated"


class BillingStatus(enum.StrEnum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    # Doc 3 roadmap (Phase 4, manual/CliQ-style billing) — an owner has requested a paid tier
    # and been shown payment instructions; only a manual DB confirmation (no self-serve button
    # — see db/models.py's Subscription docstring) flips this to active.
    payment_pending = "payment_pending"


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    channels_connected: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # The Facebook user who completed the self-serve WhatsApp/Page signup (onboarding/
    # meta_oauth.py's get_authorizing_user_id) — never set for manually-onboarded businesses.
    # Meta's deauthorize/data-deletion platform callbacks (api/meta_compliance.py) only ever
    # receive this same id, never a business_id, so without it those callbacks can't act on
    # anything. Not unique: whichever signup flow ran last wins if a business somehow used two
    # different Facebook accounts for WhatsApp vs. Page login — an accepted MVP limitation
    # (Doc 1's target seller is solo/small, one person doing both).
    facebook_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_tier: Mapped[PlanTier] = mapped_column(
        Enum(PlanTier, name="plan_tier"), nullable=False, default=PlanTier.starter
    )
    brand_voice_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    escalation_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # The shop's own origin location — Doc 2 Section 9.1's estimate_delivery node needs this
    # as the Google Maps origin. Nullable: only businesses using delivery-estimation need it.
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Shape: {"cutoff_hour": 15, "min_lead_hours": 6} (Doc 2 Section 9.3). Owner-editable UI
    # is Phase 6e+; for now this is seeded directly per business, same as escalation_rules.
    delivery_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # "I'm not available today" (Doc 3 roadmap, partner meeting 2026-09-01) — while true, every
    # incoming message gets away_message (or a translated default) instead of the normal
    # pipeline; see graph/routers.py's load_context_router and graph/nodes/send_away_reply.py.
    is_away: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    away_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    knowledge_documents: Mapped[list["KnowledgeDocument"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    customers: Mapped[list["Customer"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    subscription: Mapped["Subscription | None"] = relationship(
        back_populates="business", cascade="all, delete-orphan", uselist=False
    )
    orders: Mapped[list["Order"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    users: Mapped[list["User"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_businesses_facebook_user_id", "facebook_user_id"),)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[KnowledgeDocType] = mapped_column(
        Enum(KnowledgeDocType, name="knowledge_doc_type"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Structured fields for exact lookups (price, variants, stock) that retrieve_knowledge
    # queries directly rather than via vector similarity — see Doc 2 Section 2.2 (hybrid retrieval).
    structured_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    embedding_vector: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True
    )
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Time-bound promotional content (Doc 3 Phase 6.5) — only ever set on type=promotion rows,
    # NULL for everything else. graph/nodes/retrieve_knowledge.py filters on these unconditionally
    # (a blanket NULL-or-in-range check), which is safe precisely because no other type touches
    # them. Real columns rather than structured_data fields since they must be filterable in SQL.
    active_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship(back_populates="knowledge_documents")

    __table_args__ = (Index("ix_knowledge_documents_business_id", "business_id"),)


class Order(Base):
    """Spreadsheet-fallback order data (Doc 2 Section 2.6) — synced from a seller's order
    sheet, not a live storefront API (that's Salla/Zid/Shopify, Phase 3+). Looked up by phone
    number since that's how sellers actually track orders, which also happens to match
    Customer.channel_handle for WhatsApp customers (orders/phone.py normalizes both sides).
    """

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    order_reference: Mapped[str] = mapped_column(Text, nullable=False)
    customer_phone: Mapped[str] = mapped_column(Text, nullable=False)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free text, not an enum — sellers use their own status vocabulary ("processing",
    # "shipped", "على الطريق", ...); a spreadsheet fallback shouldn't force a fixed taxonomy.
    status: Mapped[str] = mapped_column(Text, nullable=False)
    items_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The three fields below are only populated for orders placed live through a conversation
    # (graph/nodes/estimate_delivery.py, Doc 2 Section 9.1) — spreadsheet-synced orders never
    # set them. delivery_status is deliberately a separate column from the free-text `status`
    # above: the backlog COUNT query (Doc 2 Section 9.3) needs one unambiguous value to filter
    # on, not every seller's own status vocabulary.
    delivery_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_window_promised: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Doc 3 roadmap (order confirmation layer) — nullable, see OrderConfirmationStatus docstring.
    confirmation_status: Mapped[OrderConfirmationStatus | None] = mapped_column(
        Enum(OrderConfirmationStatus, name="order_confirmation_status"), nullable=True
    )
    # Doc 3 roadmap (order confirmation follow-up nudge) — set the moment the confirmation-
    # request draft is actually sent (graph/nodes/update_memory.py), not when this row is
    # created (estimate_delivery.py creates it earlier, before self_check/confidence_router
    # have decided whether that draft actually reaches the customer or escalates instead).
    # Also the base the delayed nudge job schedules itself from (queue/tasks.py).
    confirmation_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Idempotency guard for the nudge job (worker.py) — confirmation_status deliberately stays
    # "pending" after a nudge (the plan: leave it pending if still no reply, never auto-cancel/
    # escalate), so confirmation_status alone can't tell the job "already nudged, don't send a
    # second one." Set once, the first (and only) time a nudge actually sends.
    confirmation_nudge_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship(back_populates="orders")

    __table_args__ = (
        UniqueConstraint("business_id", "order_reference", name="uq_order_reference"),
        Index("ix_orders_business_id_customer_phone", "business_id", "customer_phone"),
    )


class User(Base):
    """A business owner's own login (Doc 3: dashboard access needs auth before real sellers
    use it — not in the original data model doc, added once the dashboard itself existed).
    Multiple users per business are allowed (staff accounts) — nothing here assumes exactly one.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    # Doc 3 roadmap (partner meeting 2026-09-01) — recorded at signup once the ToS/Privacy
    # checkbox is required there; nullable because accounts created before this feature existed
    # never accepted anything through this flow (grandfathered, not retroactively backfilled).
    accepted_terms_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship(back_populates="users")

    __table_args__ = (Index("ix_users_business_id", "business_id"),)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[ChannelType] = mapped_column(
        Enum(ChannelType, name="channel_type"), nullable=False
    )
    channel_handle: Mapped[str] = mapped_column(Text, nullable=False)
    profile_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    order_history_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship(back_populates="customers")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="customer")

    __table_args__ = (
        UniqueConstraint("business_id", "channel", "channel_handle", name="uq_customer_identity"),
        Index("ix_customers_business_id", "business_id"),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[ChannelType] = mapped_column(
        Enum(ChannelType, name="channel_type"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status"),
        nullable=False,
        default=ConversationStatus.auto,
    )
    # LangGraph checkpointer thread id (channel + customer scoped) — links a conversation
    # row to its durable graph state without duplicating it (Doc 2 Section 2.3 / 4).
    thread_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship(back_populates="conversations")
    customer: Mapped["Customer"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    escalations: Mapped[list["Escalation"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_conversations_business_id", "business_id"),)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection, name="message_direction"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    intent_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Meta's per-message id, used for webhook dedup/idempotency (Doc 2 Section 2.1).
    channel_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        UniqueConstraint("channel_message_id", name="uq_messages_channel_message_id"),
    )


class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    drafted_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EscalationStatus] = mapped_column(
        Enum(EscalationStatus, name="escalation_status"),
        nullable=False,
        default=EscalationStatus.pending,
    )
    resolved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="escalations")

    __table_args__ = (Index("ix_escalations_conversation_id", "conversation_id"),)


class ApprovalRequest(Base):
    """Distinct from Escalation (Doc 2 Section 9.2): fires when the agent IS confident in a
    computed delivery estimate, but a same-day commitment is consequential enough that it
    still needs the owner's sign-off before reaching the customer — not a case of the agent
    being unsure. See graph/nodes/request_owner_approval.py.
    """

    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    drafted_reply: Mapped[str] = mapped_column(Text, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    # Links back to the Order row estimate_delivery already wrote (uq_order_reference) — lets
    # the reject route update it to reflect "tomorrow" instead of the declined same-day promise,
    # without a second migration on the orders table.
    order_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The two fields below exist for adaptive autonomy (Doc 2 Section 9.4,
    # graph/nodes/request_owner_approval.py's _matches_learned_pattern) — a business earns
    # auto-approval for a specific (business_id, estimated_window) pattern once its last N
    # resolved requests in that pattern are all approved with sent_unchanged=True.
    # estimated_window doubles as the pattern-matching key: it's already the exact string shown
    # to both the owner and the customer, so reusing it avoids inventing new numeric bucket
    # boundaries the doc doesn't specify.
    estimated_window: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_unchanged: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[ApprovalRequestStatus] = mapped_column(
        Enum(ApprovalRequestStatus, name="approval_request_status"),
        nullable=False,
        default=ApprovalRequestStatus.pending,
    )
    resolved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="approval_requests")

    __table_args__ = (Index("ix_approval_requests_conversation_id", "conversation_id"),)


class Subscription(Base):
    """billing_status transitions (Doc 3 roadmap, Phase 4 manual/CliQ-style billing):
    trialing -> payment_pending (owner requests a paid tier, api/dashboard.py's
    request_plan route) -> active (manual DB confirmation only, once OptiGnosis has actually
    verified the transfer arrived — deliberately no self-serve "mark my own payment confirmed"
    button, same reviewed-not-automatic precedent as CustomRule's approval flow).
    """

    __tablename__ = "subscriptions"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
    )
    tier: Mapped[PlanTier] = mapped_column(Enum(PlanTier, name="plan_tier"), nullable=False)
    message_usage_current_period: Mapped[int] = mapped_column(nullable=False, default=0)
    billing_status: Mapped[BillingStatus] = mapped_column(
        Enum(BillingStatus, name="billing_status"), nullable=False, default=BillingStatus.trialing
    )
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    business: Mapped["Business"] = relationship(back_populates="subscription")


class PushSubscription(Base):
    """A single browser/device's Web Push subscription (Doc 3 Phase 6.6, notifications/
    push.py) — keyed on (business_id, user_id) since User already anticipates multiple staff
    logins per business, each potentially subscribing their own device. endpoint is unique:
    a subscription is naturally idempotent per browser install, and the endpoint URL itself
    (not id) is what a re-subscribe from the same device would collide on.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh_key: Mapped[str] = mapped_column(Text, nullable=False)
    auth_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_push_subscriptions_business_id", "business_id"),
        UniqueConstraint("endpoint", name="uq_push_subscriptions_endpoint"),
    )


class CustomRule(Base):
    """A free-text rule an owner submits from the dashboard's Rules page (Doc 3 roadmap,
    partner meeting 2026-09-01: "better to contact us... so we make sure the agent will behave
    in the way that is acceptable"). Pending by default and inert — graph/nodes/
    generate_response.py only injects status=approved rules into the prompt. No dedicated
    review UI yet: reviewed via direct DB access (reviewed_by is free text, not an admin-user
    FK — there's no admin-user model in this codebase, same convention as Escalation.resolved_by
    already using a free-text field rather than a real user reference).
    """

    __tablename__ = "custom_rules"

    id: Mapped[uuid.UUID] = _uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CustomRuleStatus] = mapped_column(
        Enum(CustomRuleStatus, name="custom_rule_status"),
        nullable=False,
        default=CustomRuleStatus.pending,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_custom_rules_business_id", "business_id"),)
