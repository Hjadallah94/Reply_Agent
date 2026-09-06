"""api/public.py — deliberately unauthenticated routes, no TestClient login needed. Real DB."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from reply_agent.api.app import app
from reply_agent.db.models import (
    Business,
    KnowledgeDocType,
    KnowledgeDocument,
    PlanTier,
    ProductImage,
)
from reply_agent.db.session import get_sessionmaker

BUSINESS_NAME = "Public Route Test Business"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
async def product_with_image():
    async with get_sessionmaker()() as session:
        business = Business(name=BUSINESS_NAME, plan_tier=PlanTier.starter)
        session.add(business)
        await session.flush()

        document = KnowledgeDocument(
            business_id=business.id,
            type=KnowledgeDocType.product,
            content="Product: Camel Wool Scarf\nPrice: 12 JOD",
            structured_data={"name": "Camel Wool Scarf", "price_jod": 12},
        )
        session.add(document)
        await session.flush()

        session.add(
            ProductImage(
                document_id=document.id, image_data=b"real-image-bytes", content_type="image/jpeg"
            )
        )
        await session.commit()
        await session.refresh(document)

        yield document

        await session.execute(delete(Business).where(Business.id == business.id))
        await session.commit()


async def test_product_image_route_returns_the_stored_bytes(client, product_with_image):
    response = client.get(f"/public/products/{product_with_image.id}/image")

    assert response.status_code == 200
    assert response.content == b"real-image-bytes"
    assert response.headers["content-type"] == "image/jpeg"


async def test_product_image_route_404s_when_no_image_exists(client):
    response = client.get(f"/public/products/{uuid.uuid4()}/image")

    assert response.status_code == 404
