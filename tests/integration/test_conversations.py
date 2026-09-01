"""Dashboard "All conversations" list + detail + owner-DM send routes (Doc 3 roadmap, partner
meeting 2026-09-01, item 6) — real DB, create_logged_in_business (tests/auth_helpers.py), mocked
WhatsApp send (same pattern as test_send_away_reply.py).
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from reply_agent.api.app import app
from reply_agent.db.models import (
    ApprovalRequest,
    ApprovalRequestStatus,
    Business,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Escalation,
    EscalationStatus,
    Message,
    MessageDirection,
)
from reply_agent.db.session import get_sessionmaker
from tests.auth_helpers import create_logged_in_business, dispose_engines

BUSINESS_NAME = "Conversations Test Business"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
async def business(client):
    b = await create_logged_in_business(client, BUSINESS_NAME)
    async with get_sessionmaker()() as session:
        db_business = await session.get(Business, b.id)
        db_business.channels_connected = {"whatsapp": {"phone_number_id": "test-phone-number-id"}}
        await session.commit()
    await dispose_engines()
    yield b
    await dispose_engines()
    async with get_sessionmaker()() as session:
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


async def _seed_conversation(business_id: uuid.UUID, *, phone: str, with_messages: bool = True):
    async with get_sessionmaker()() as session:
        customer = Customer(
            business_id=business_id, channel=ChannelType.whatsapp, channel_handle=phone
        )
        session.add(customer)
        await session.flush()

        conv = Conversation(
            business_id=business_id,
            channel=ChannelType.whatsapp,
            customer_id=customer.id,
            status=ConversationStatus.auto,
            thread_id=f"whatsapp:{business_id}:{phone}",
        )
        session.add(conv)
        await session.flush()

        if with_messages:
            session.add(
                Message(
                    conversation_id=conv.id,
                    direction=MessageDirection.inbound,
                    text="Do you have cookies?",
                )
            )
        await session.commit()
        await session.refresh(conv)
        return conv


async def test_conversations_list_renders_seeded_conversations(client, business):
    await _seed_conversation(business.id, phone="962790010001")
    await dispose_engines()

    response = client.get(f"/businesses/{business.id}/dashboard/conversations")

    assert response.status_code == 200
    assert "962790010001" in response.text
    assert "Do you have cookies?" in response.text


async def test_conversations_list_paginates(client, business):
    for i in range(3):
        await _seed_conversation(business.id, phone=f"96279002000{i}")
    await dispose_engines()

    response = client.get(f"/businesses/{business.id}/dashboard/conversations?page=1")
    assert response.status_code == 200

    await dispose_engines()
    response_bad_page = client.get(f"/businesses/{business.id}/dashboard/conversations?page=0")
    assert response_bad_page.status_code == 200


async def test_conversation_detail_shows_full_transcript(client, business):
    conv = await _seed_conversation(business.id, phone="962790010002")
    await dispose_engines()

    response = client.get(f"/businesses/{business.id}/dashboard/conversations/{conv.id}")

    assert response.status_code == 200
    assert "962790010002" in response.text
    assert "Do you have cookies?" in response.text


async def test_conversation_detail_404s_for_unowned_business(client, business):
    conv = await _seed_conversation(business.id, phone="962790010003")
    await dispose_engines()
    unowned = "00000000-0000-0000-0000-000000000000"

    response = client.get(f"/businesses/{unowned}/dashboard/conversations/{conv.id}")

    assert response.status_code == 404


async def test_send_conversation_message_sends_and_writes_outbound_message(client, business):
    conv = await _seed_conversation(business.id, phone="962790010004")
    await dispose_engines()

    with patch(
        "reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()
    ) as mock_send:
        response = client.post(
            f"/businesses/{business.id}/dashboard/conversations/{conv.id}/send",
            data={"reply_text": "Hey! Yes we do."},
            follow_redirects=False,
        )

    assert response.status_code == 303
    mock_send.assert_called_once_with(
        to="962790010004", text="Hey! Yes we do.", phone_number_id="test-phone-number-id"
    )

    await dispose_engines()
    async with get_sessionmaker()() as session:
        outbound = await session.scalar(
            select(Message).where(
                Message.conversation_id == conv.id,
                Message.direction == MessageDirection.outbound,
            )
        )
        assert outbound is not None
        assert outbound.text == "Hey! Yes we do."
        assert outbound.model_used == "owner"


async def test_send_conversation_message_normalizes_crlf(client, business):
    conv = await _seed_conversation(business.id, phone="962790010005")
    await dispose_engines()

    with patch("reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()):
        client.post(
            f"/businesses/{business.id}/dashboard/conversations/{conv.id}/send",
            data={"reply_text": "Line one\r\nLine two"},
            follow_redirects=False,
        )

    await dispose_engines()
    async with get_sessionmaker()() as session:
        outbound = await session.scalar(
            select(Message).where(
                Message.conversation_id == conv.id,
                Message.direction == MessageDirection.outbound,
            )
        )
        assert outbound.text == "Line one\nLine two"


async def test_send_conversation_message_rejects_blank_text(client, business):
    conv = await _seed_conversation(business.id, phone="962790010006")
    await dispose_engines()

    response = client.post(
        f"/businesses/{business.id}/dashboard/conversations/{conv.id}/send",
        data={"reply_text": "   "},
    )

    assert response.status_code == 400


async def test_conversation_detail_shows_banner_for_pending_escalation(client, business):
    conv = await _seed_conversation(business.id, phone="962790010007")
    async with get_sessionmaker()() as session:
        session.add(
            Escalation(
                conversation_id=conv.id,
                reason="Risk category: legal_threat",
                status=EscalationStatus.pending,
            )
        )
        await session.commit()
    await dispose_engines()

    response = client.get(f"/businesses/{business.id}/dashboard/conversations/{conv.id}")

    assert response.status_code == 200
    assert "escalation" in response.text.lower()


async def test_conversation_detail_shows_banner_for_pending_approval(client, business):
    conv = await _seed_conversation(business.id, phone="962790010008")
    async with get_sessionmaker()() as session:
        session.add(
            ApprovalRequest(
                conversation_id=conv.id,
                drafted_reply="Confirming your order...",
                reasoning="Same-day delivery commitment",
                status=ApprovalRequestStatus.pending,
            )
        )
        await session.commit()
    await dispose_engines()

    response = client.get(f"/businesses/{business.id}/dashboard/conversations/{conv.id}")

    assert response.status_code == 200
    assert "approval" in response.text.lower()
