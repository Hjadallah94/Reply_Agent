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


class BillingStatus(enum.StrEnum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    channels_connected: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    plan_tier: Mapped[PlanTier] = mapped_column(
        Enum(PlanTier, name="plan_tier"), nullable=False, default=PlanTier.starter
    )
    brand_voice_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    escalation_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
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


class Subscription(Base):
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
