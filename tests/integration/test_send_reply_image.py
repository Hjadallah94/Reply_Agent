"""graph/nodes/send_reply.py's product-photo dispatch (Doc 3 roadmap, "agent can send photo
samples") — real DB (tenant_session, KnowledgeDocument/ProductImage rows), mocked WhatsApp
sends (same pattern as test_send_away_reply.py).
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete

from reply_agent.db.models import (
    Business,
    KnowledgeDocType,
    KnowledgeDocument,
    PlanTier,
    ProductImage,
)
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.nodes.send_reply import send_reply

CUSTOMER_PHONE = "962790007777"
THREAD_ID = f"whatsapp:business:{CUSTOMER_PHONE}"


@pytest.fixture
async def business():
    async with get_sessionmaker()() as session:
        b = Business(
            name="Send Reply Image Test Business",
            plan_tier=PlanTier.starter,
            channels_connected={"whatsapp": {"phone_number_id": "test-phone-number-id"}},
        )
        session.add(b)
        await session.commit()
        await session.refresh(b)
        yield b
        await session.execute(
            delete(KnowledgeDocument).where(KnowledgeDocument.business_id == b.id)
        )
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


@pytest.fixture
async def product_with_image(business):
    async with get_sessionmaker()() as session:
        document = KnowledgeDocument(
            business_id=business.id,
            type=KnowledgeDocType.product,
            content="Product: Dead Sea Salt Set\nPrice: 8 JOD",
            structured_data={"name": "Dead Sea Salt Set", "price_jod": 8},
        )
        session.add(document)
        await session.flush()
        session.add(
            ProductImage(document_id=document.id, image_data=b"bytes", content_type="image/png")
        )
        await session.commit()
        await session.refresh(document)
        yield document


def _state(business_id: uuid.UUID, cited_sources: list[str]) -> dict:
    return {
        "channel": "whatsapp",
        "business_id": str(business_id),
        "thread_id": THREAD_ID,
        "draft_reply": {"text": "It's 8 JOD, in stock!", "cited_sources": cited_sources},
    }


async def test_sends_the_cited_products_photo_after_the_text_reply(business, product_with_image):
    state = _state(business.id, [str(product_with_image.id)])

    with (
        patch("reply_agent.graph.nodes.send_reply.get_settings") as mock_settings,
        patch("reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()),
        patch(
            "reply_agent.graph.nodes.send_reply.send_whatsapp_image", new=AsyncMock()
        ) as mock_image,
    ):
        mock_settings.return_value.app_base_url = "https://staging.example.com"
        result = await send_reply(state)

    assert result == {"route": "send"}
    mock_image.assert_called_once_with(
        to=CUSTOMER_PHONE,
        image_url=f"https://staging.example.com/public/products/{product_with_image.id}/image",
        phone_number_id="test-phone-number-id",
        caption="Dead Sea Salt Set — 8 JOD",
    )


async def test_no_image_sent_when_app_base_url_not_configured(business, product_with_image):
    state = _state(business.id, [str(product_with_image.id)])

    with (
        patch("reply_agent.graph.nodes.send_reply.get_settings") as mock_settings,
        patch("reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()),
        patch(
            "reply_agent.graph.nodes.send_reply.send_whatsapp_image", new=AsyncMock()
        ) as mock_image,
    ):
        mock_settings.return_value.app_base_url = ""
        await send_reply(state)

    mock_image.assert_not_called()


async def test_no_image_sent_when_no_cited_product_has_one(business):
    async with get_sessionmaker()() as session:
        document = KnowledgeDocument(
            business_id=business.id,
            type=KnowledgeDocType.product,
            content="Product: Plain Postcard\nPrice: 1 JOD",
            structured_data={"name": "Plain Postcard", "price_jod": 1},
        )
        session.add(document)
        await session.commit()
        await session.refresh(document)

    state = _state(business.id, [str(document.id)])

    with (
        patch("reply_agent.graph.nodes.send_reply.get_settings") as mock_settings,
        patch("reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()),
        patch(
            "reply_agent.graph.nodes.send_reply.send_whatsapp_image", new=AsyncMock()
        ) as mock_image,
    ):
        mock_settings.return_value.app_base_url = "https://staging.example.com"
        await send_reply(state)

    mock_image.assert_not_called()


async def test_non_uuid_cited_sources_are_skipped_without_error(business):
    state = _state(business.id, [f"order:{uuid.uuid4()}"])

    with (
        patch("reply_agent.graph.nodes.send_reply.get_settings") as mock_settings,
        patch("reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()),
        patch(
            "reply_agent.graph.nodes.send_reply.send_whatsapp_image", new=AsyncMock()
        ) as mock_image,
    ):
        mock_settings.return_value.app_base_url = "https://staging.example.com"
        result = await send_reply(state)

    assert result == {"route": "send"}
    mock_image.assert_not_called()


async def test_no_image_sent_when_draft_has_no_cited_sources(business):
    """The shape send_away_reply.py/send_order_catalog_reply.py actually pass to send_reply —
    proves this stays a no-op for them without any extra route-checking in send_reply itself.
    """
    state = {
        "channel": "whatsapp",
        "business_id": str(business.id),
        "thread_id": THREAD_ID,
        "draft_reply": {"text": "We're away today!"},
    }

    with (
        patch("reply_agent.graph.nodes.send_reply.get_settings") as mock_settings,
        patch("reply_agent.graph.nodes.send_reply.send_whatsapp_message", new=AsyncMock()),
        patch(
            "reply_agent.graph.nodes.send_reply.send_whatsapp_image", new=AsyncMock()
        ) as mock_image,
    ):
        mock_settings.return_value.app_base_url = "https://staging.example.com"
        await send_reply(state)

    mock_image.assert_not_called()
