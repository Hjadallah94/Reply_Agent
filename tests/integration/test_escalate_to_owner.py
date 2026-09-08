"""graph/nodes/escalate_to_owner.py — no dedicated test file existed before this (Doc 3 Phase
6.6's push-notification addition is what prompted adding one). Real DB (tenant_session,
Conversation/Escalation rows), mocked WhatsApp send and push send.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from reply_agent.db.models import (
    Business,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Escalation,
    EscalationStatus,
    PlanTier,
)
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.nodes.escalate_to_owner import escalate_to_owner
from reply_agent.graph.nodes.load_context import load_context

THREAD_ID_TEMPLATE = "whatsapp:{business_id}:962790004444"


@pytest.fixture
async def business():
    async with get_sessionmaker()() as session:
        b = Business(
            name="Escalate To Owner Test Business",
            plan_tier=PlanTier.starter,
            channels_connected={"whatsapp": {"phone_number_id": "test-phone-number-id"}},
        )
        session.add(b)
        await session.commit()
        await session.refresh(b)
        yield b
        await session.execute(
            delete(Escalation).where(
                Escalation.conversation_id.in_(
                    select(Conversation.id).where(Conversation.business_id == b.id)
                )
            )
        )
        await session.execute(delete(Conversation).where(Conversation.business_id == b.id))
        await session.execute(delete(Customer).where(Customer.business_id == b.id))
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


@pytest.fixture
async def conversation(business):
    async with get_sessionmaker()() as session:
        customer = Customer(
            business_id=business.id, channel=ChannelType.whatsapp, channel_handle="962790004444"
        )
        session.add(customer)
        await session.flush()

        conv = Conversation(
            business_id=business.id,
            channel=ChannelType.whatsapp,
            customer_id=customer.id,
            status=ConversationStatus.auto,
            thread_id=THREAD_ID_TEMPLATE.format(business_id=business.id),
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        yield conv


def _state(business_id: uuid.UUID, thread_id: str) -> dict:
    return {
        "business_id": str(business_id),
        "thread_id": thread_id,
        "message": {
            "text": "This is a scam, I'm reporting you",
            "media_refs": [],
            "received_at": "2026-08-30T12:00:00Z",
            "channel_message_id": "wamid.test",
        },
        "draft_reply": {"text": "", "cited_sources": [], "model_used": "claude"},
        "intent": {"label": "legal_threat", "confidence": 0.9, "sentiment": "negative"},
    }


async def test_writes_an_escalation_row(business, conversation):
    state = _state(business.id, conversation.thread_id)

    with (
        patch("reply_agent.graph.nodes.escalate_to_owner.send_text_message", new=AsyncMock()),
        patch("reply_agent.graph.nodes.escalate_to_owner.send_push_to_business", new=AsyncMock()),
    ):
        result = await escalate_to_owner(state)

    assert result["route"] == "escalate"

    async with get_sessionmaker()() as session:
        escalation = await session.scalar(
            select(Escalation).where(Escalation.conversation_id == conversation.id)
        )
        assert escalation is not None

        refreshed_conversation = await session.get(Conversation, conversation.id)
        assert refreshed_conversation.status == ConversationStatus.owner_handled


async def test_agent_disabled_reaches_escalation_with_override_reason_and_no_intent(
    business, conversation
):
    """Doc 3 roadmap (agent on/off toggle) — routers.py's load_context_router routes here
    directly when the owner has turned the agent off, before classify_intent/generate_response
    ever run. load_context.py sets only escalation_override_reason, no intent/draft_reply at
    all — proves escalate_to_owner (and its _escalation_reason helper) handles that minimal
    shape correctly rather than assuming a fuller state always reaches it.
    """
    state = {
        "business_id": str(business.id),
        "thread_id": conversation.thread_id,
        "message": {
            "text": "Do you have this in blue?",
            "media_refs": [],
            "received_at": "2026-09-06T12:00:00Z",
            "channel_message_id": "wamid.agent-disabled-test",
        },
        "escalation_override_reason": "Agent turned off — business is replying manually",
    }

    with (
        patch("reply_agent.graph.nodes.escalate_to_owner.send_text_message", new=AsyncMock()),
        patch("reply_agent.graph.nodes.escalate_to_owner.send_push_to_business", new=AsyncMock()),
    ):
        result = await escalate_to_owner(state)

    assert result["route"] == "escalate"
    assert result["escalation"]["reason"] == "Agent turned off — business is replying manually"

    async with get_sessionmaker()() as session:
        escalation = await session.scalar(
            select(Escalation).where(Escalation.conversation_id == conversation.id)
        )
        assert escalation is not None
        assert escalation.reason == "Agent turned off — business is replying manually"
        assert escalation.drafted_reply is None


async def test_push_notification_sent_alongside_whatsapp_ping(business, conversation):
    """Web Push (Doc 3 Phase 6.6) supplements, never replaces, the existing WhatsApp ping."""
    state = _state(business.id, conversation.thread_id)

    with (
        patch(
            "reply_agent.graph.nodes.escalate_to_owner.send_text_message", new=AsyncMock()
        ) as mock_whatsapp,
        patch(
            "reply_agent.graph.nodes.escalate_to_owner.send_push_to_business", new=AsyncMock()
        ) as mock_push,
        patch("reply_agent.graph.nodes.escalate_to_owner.get_settings") as mock_settings,
    ):
        mock_settings.return_value.owner_notification_whatsapp_number = "962790009999"
        mock_settings.return_value.app_base_url = "https://staging.example.com"
        await escalate_to_owner(state)

    mock_whatsapp.assert_called_once()
    mock_push.assert_called_once()
    call_args = mock_push.call_args
    assert call_args.args[1] == business.id
    assert call_args.kwargs["url"].startswith(
        f"https://staging.example.com/businesses/{business.id}/dashboard/escalations/"
    )


async def test_no_push_url_when_app_base_url_not_configured(business, conversation):
    state = _state(business.id, conversation.thread_id)

    with (
        patch("reply_agent.graph.nodes.escalate_to_owner.send_text_message", new=AsyncMock()),
        patch(
            "reply_agent.graph.nodes.escalate_to_owner.send_push_to_business", new=AsyncMock()
        ) as mock_push,
        patch("reply_agent.graph.nodes.escalate_to_owner.get_settings") as mock_settings,
    ):
        mock_settings.return_value.owner_notification_whatsapp_number = ""
        mock_settings.return_value.app_base_url = ""
        await escalate_to_owner(state)

    mock_push.assert_called_once()
    assert mock_push.call_args.kwargs["url"] == ""


# --- load_context's open-risk-escalation surfacing -----------------------------------------
# Doc 3 roadmap (real gap found live, 12-message Petra Treasures conversation test, 2026-09-07):
# a price-negotiation escalation must not get quietly resolved by a later, differently-topiced
# reply just because it resurfaces in conversation_history. load_context.py surfaces this
# conversation's still-pending risk-category escalation reasons so generate_response.py can tell
# the model not to.


async def _seed_escalation(conversation_id: uuid.UUID, *, reason: str, status: EscalationStatus):
    async with get_sessionmaker()() as session:
        escalation = Escalation(conversation_id=conversation_id, reason=reason, status=status)
        session.add(escalation)
        await session.commit()
        await session.refresh(escalation)
        return escalation


def _load_context_state(
    business_id: uuid.UUID, customer_id: uuid.UUID, thread_id: str, channel_message_id: str
) -> dict:
    return {
        "business_id": str(business_id),
        "customer_id": str(customer_id),
        "channel": "whatsapp",
        "thread_id": thread_id,
        "message": {
            "text": "what about something under 10 JOD?",
            "media_refs": [],
            "received_at": "2026-09-07T14:02:00Z",
            "channel_message_id": channel_message_id,
        },
    }


async def test_load_context_surfaces_a_pending_risk_category_escalation(business, conversation):
    await _seed_escalation(
        conversation.id,
        reason="Risk category: price_negotiation",
        status=EscalationStatus.pending,
    )

    result = await load_context(
        _load_context_state(
            business.id, conversation.customer_id, conversation.thread_id, "wamid.open-risk-1"
        )
    )

    assert result["open_risk_escalation_reasons"] == ["Risk category: price_negotiation"]


async def test_load_context_excludes_a_resolved_escalation(business, conversation):
    await _seed_escalation(
        conversation.id,
        reason="Risk category: price_negotiation",
        status=EscalationStatus.resolved,
    )

    result = await load_context(
        _load_context_state(
            business.id, conversation.customer_id, conversation.thread_id, "wamid.open-risk-2"
        )
    )

    assert result["open_risk_escalation_reasons"] == []


async def test_load_context_excludes_a_pending_capability_gap_escalation(business, conversation):
    await _seed_escalation(
        conversation.id,
        reason="No place order capability yet — needs a human answer",
        status=EscalationStatus.pending,
    )

    result = await load_context(
        _load_context_state(
            business.id, conversation.customer_id, conversation.thread_id, "wamid.open-risk-3"
        )
    )

    assert result["open_risk_escalation_reasons"] == []


async def test_load_context_with_no_pending_escalations_returns_empty_list(business, conversation):
    result = await load_context(
        _load_context_state(
            business.id, conversation.customer_id, conversation.thread_id, "wamid.open-risk-4"
        )
    )

    assert result["open_risk_escalation_reasons"] == []
