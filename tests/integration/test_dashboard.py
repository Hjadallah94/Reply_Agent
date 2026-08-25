"""Owner dashboard (Doc 3 Phase 3). Real DB; the only thing mocked is the outbound channel
send, same pattern as tests/unit/test_send_reply.py. Every route here is gated by
auth/dependencies.py — tests log in via tests/auth_helpers.py the same way a browser would.
"""

from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import delete, select

from reply_agent.api.app import app
from reply_agent.db.models import (
    Business,
    ChannelType,
    Conversation,
    ConversationStatus,
    Customer,
    Escalation,
    EscalationStatus,
    KnowledgeDocType,
    KnowledgeDocument,
    Message,
    MessageDirection,
)
from reply_agent.db.session import get_sessionmaker
from tests.auth_helpers import create_logged_in_business, dispose_engines

BUSINESS_NAME = "Dashboard Test Business"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
async def escalation(client):
    business = await create_logged_in_business(client, BUSINESS_NAME)

    async with get_sessionmaker()() as session:
        db_business = await session.get(Business, business.id)
        db_business.channels_connected = {"whatsapp": {"phone_number_id": "test-phone-number-id"}}

        customer = Customer(
            business_id=business.id,
            channel=ChannelType.whatsapp,
            channel_handle="962790001111",
        )
        session.add(customer)
        await session.flush()

        conversation = Conversation(
            business_id=business.id,
            channel=ChannelType.whatsapp,
            customer_id=customer.id,
            status=ConversationStatus.owner_handled,
            thread_id=f"whatsapp:{business.id}:962790001111",
        )
        session.add(conversation)
        await session.flush()

        session.add(
            Message(
                conversation_id=conversation.id,
                direction=MessageDirection.inbound,
                text="Can I get a refund?",
            )
        )

        escalation = Escalation(
            conversation_id=conversation.id,
            reason="refund_or_complaint always escalates",
            drafted_reply="Sorry, no cash refunds — exchanges only.",
            status=EscalationStatus.pending,
        )
        session.add(escalation)
        await session.commit()
        await session.refresh(escalation)

    # About to hand control to the test body, which makes its own TestClient calls — same
    # cross-loop issue as create_logged_in_business's own dispose, needed again here since
    # this fixture did more direct session work afterward.
    await dispose_engines()
    yield business, escalation

    # The test body made its own TestClient calls after this session block closed — same
    # cross-loop issue create_logged_in_business's own dispose handles, needed again here
    # before this fixture's own teardown DB access.
    await dispose_engines()
    async with get_sessionmaker()() as session:
        await session.execute(delete(Business).where(Business.id == business.id))
        await session.commit()


async def test_dashboard_redirects_to_the_logged_in_user_own_business(client, escalation):
    business, _ = escalation
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/businesses/{business.id}/dashboard"


async def test_dashboard_redirects_to_login_when_not_authenticated():
    client = TestClient(app)
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


async def test_business_dashboard_lists_the_escalation(client, escalation):
    business, esc = escalation
    response = client.get(f"/businesses/{business.id}/dashboard")
    assert response.status_code == 200
    assert "962790001111" in response.text
    assert f"/dashboard/escalations/{esc.id}" in response.text


async def test_business_dashboard_404s_for_unknown_business(client, escalation):
    # Logged in, but to a different business than the one being requested.
    response = client.get("/businesses/00000000-0000-0000-0000-000000000000/dashboard")
    assert response.status_code == 404


async def test_business_dashboard_redirects_to_login_when_not_authenticated(escalation):
    business, _ = escalation
    anonymous_client = TestClient(app)
    response = anonymous_client.get(f"/businesses/{business.id}/dashboard", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


async def test_escalation_detail_shows_draft_and_reason(client, escalation):
    business, esc = escalation
    response = client.get(f"/businesses/{business.id}/dashboard/escalations/{esc.id}")
    assert response.status_code == 200
    assert "refund_or_complaint always escalates" in response.text
    assert "Sorry, no cash refunds" in response.text
    assert "Can I get a refund?" in response.text


async def test_resolve_sends_updates_db_and_redirects(client, escalation):
    business, esc = escalation

    with (
        patch(
            "reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()
        ) as mock_send,
        patch(
            "reply_agent.knowledge.corrections.embed_documents",
            return_value=[[0.0] * 1024],
        ),
    ):
        response = client.post(
            f"/businesses/{business.id}/dashboard/escalations/{esc.id}/resolve",
            data={"reply_text": "Edited final reply"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/businesses/{business.id}/dashboard"
    mock_send.assert_called_once_with(
        to="962790001111", text="Edited final reply", phone_number_id="test-phone-number-id"
    )

    await dispose_engines()

    async with get_sessionmaker()() as session:
        refreshed = await session.get(Escalation, esc.id)
        assert refreshed.status == EscalationStatus.resolved
        assert refreshed.resolved_by == "owner"
        assert refreshed.resolution_text == "Edited final reply"

        conversation = await session.get(Conversation, esc.conversation_id)
        assert conversation.status == ConversationStatus.auto

        outbound = await session.scalar(
            select(Message).where(
                Message.conversation_id == esc.conversation_id,
                Message.direction == MessageDirection.outbound,
            )
        )
        assert outbound.text == "Edited final reply"
        assert outbound.model_used == "owner"


async def test_resolve_with_an_edited_reply_records_a_correction(client, escalation):
    """Owner-correction feedback loop (Doc 1 Section 7) — sending something different from the
    agent's own draft should be captured as a new brand_voice few-shot example.
    """
    business, esc = escalation

    with (
        patch("reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()),
        patch(
            "reply_agent.knowledge.corrections.embed_documents",
            return_value=[[0.0] * 1024],
        ) as mock_embed,
    ):
        client.post(
            f"/businesses/{business.id}/dashboard/escalations/{esc.id}/resolve",
            data={"reply_text": "Edited final reply"},
            follow_redirects=False,
        )

    mock_embed.assert_called_once()
    embedded_text = mock_embed.call_args[0][0][0]
    assert "Can I get a refund?" in embedded_text
    assert "Edited final reply" in embedded_text

    await dispose_engines()

    async with get_sessionmaker()() as session:
        correction = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.brand_voice,
            )
        )
        assert correction is not None
        assert correction.structured_data["source"] == "owner_correction"
        assert correction.structured_data["escalation_id"] == str(esc.id)


async def test_resolve_approving_the_draft_unchanged_records_no_correction(client, escalation):
    business, esc = escalation

    with (
        patch("reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()),
        patch("reply_agent.knowledge.corrections.embed_documents") as mock_embed,
    ):
        client.post(
            f"/businesses/{business.id}/dashboard/escalations/{esc.id}/resolve",
            data={"reply_text": esc.drafted_reply},
            follow_redirects=False,
        )

    mock_embed.assert_not_called()

    await dispose_engines()

    async with get_sessionmaker()() as session:
        correction = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.brand_voice,
            )
        )
        assert correction is None


async def test_resolve_already_resolved_returns_409(client, escalation):
    business, esc = escalation

    # Set up the "already resolved" state directly via the ORM rather than a prior HTTP call —
    # two TestClient calls in one test each spin their own event loop, and the connection pool
    # from the first breaks when the second reuses it (deeper than the dispose-between-calls
    # workaround used elsewhere in this file covers).
    async with get_sessionmaker()() as session:
        db_escalation = await session.get(Escalation, esc.id)
        db_escalation.status = EscalationStatus.resolved
        await session.commit()
    await dispose_engines()

    with patch("reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()):
        response = client.post(
            f"/businesses/{business.id}/dashboard/escalations/{esc.id}/resolve",
            data={"reply_text": "Second attempt"},
        )

    assert response.status_code == 409


async def test_resolve_rejects_blank_reply(client, escalation):
    business, esc = escalation
    response = client.post(
        f"/businesses/{business.id}/dashboard/escalations/{esc.id}/resolve",
        data={"reply_text": "   "},
    )
    assert response.status_code == 400


async def test_export_returns_xlsx_with_messages(client, escalation):
    business, _esc = escalation
    response = client.get(f"/businesses/{business.id}/dashboard/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in response.headers["content-disposition"]

    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0] == (
        "Customer",
        "Channel",
        "From",
        "Message",
        "Intent",
        "Handled by",
        "Conversation status",
        "Sent at (UTC)",
    )
    assert rows[1][0] == "962790001111"
    assert rows[1][2] == "Customer"
    assert rows[1][3] == "Can I get a refund?"


async def test_export_404s_for_unknown_business(client, escalation):
    response = client.get("/businesses/00000000-0000-0000-0000-000000000000/dashboard/export")
    assert response.status_code == 404
