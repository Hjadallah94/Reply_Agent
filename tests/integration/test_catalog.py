"""Dashboard catalog CRUD (Doc 3 Phase 6.5) — real DB, create_logged_in_business (tests/
auth_helpers.py), reply_agent.knowledge.catalog.embed_documents mocked (real per-call Voyage
cost otherwise, same reasoning as every other test this session mocking embeddings).
"""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from reply_agent.api.app import app
from reply_agent.billing.tiers import CATALOG_LIMIT
from reply_agent.db.models import (
    Business,
    KnowledgeDocType,
    KnowledgeDocument,
    PlanTier,
    ProductImage,
)
from reply_agent.db.session import get_sessionmaker
from tests.auth_helpers import create_logged_in_business, dispose_engines

BUSINESS_NAME = "Catalog Test Business"
PRO_BUSINESS_NAME = "Catalog Test Business (Pro)"
EMBED_PATCH = "reply_agent.knowledge.catalog.embed_documents"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
async def business(client):
    b = await create_logged_in_business(client, BUSINESS_NAME)
    yield b
    await dispose_engines()
    async with get_sessionmaker()() as session:
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


@pytest.fixture
async def pro_business(client):
    b = await create_logged_in_business(client, PRO_BUSINESS_NAME, plan_tier=PlanTier.pro)
    yield b
    await dispose_engines()
    async with get_sessionmaker()() as session:
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


# --- Products ------------------------------------------------------------------------------


async def test_create_product(client, business):
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        response = client.post(
            f"/businesses/{business.id}/dashboard/catalog/products/new",
            data={
                "name": "Sourdough Loaf",
                "description": "Fresh-baked daily",
                "price_jod": "3.5",
                "stock_status": "in_stock",
                "variants": "small:in_stock; large:out_of_stock",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == f"/businesses/{business.id}/dashboard/catalog"

    await dispose_engines()
    async with get_sessionmaker()() as session:
        doc = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.product,
            )
        )
        assert doc is not None
        assert doc.structured_data["name"] == "Sourdough Loaf"
        assert doc.structured_data["price_jod"] == 3.5
        assert len(doc.structured_data["variants"]) == 2
        assert doc.embedding_vector is not None


async def test_create_product_rejects_bad_price(client, business):
    response = client.post(
        f"/businesses/{business.id}/dashboard/catalog/products/new",
        data={"name": "Bad", "price_jod": "not-a-number"},
    )
    assert response.status_code == 400


async def test_create_product_rejects_once_at_the_tier_catalog_limit(client, business):
    """Doc 3 roadmap (real tier differentiation, 2026-09-07) — business fixture defaults to
    Starter (CATALOG_LIMIT 20). Not retroactive by design: this only tests that a NEW create is
    blocked at the cap, never that existing products get removed.

    dispose_engines() after every call: outside a `with TestClient(...) as client:` block, each
    client.post() spins up its own fresh event loop (starlette's TestClient._portal_factory), so
    a rapid-fire loop like this one will eventually have the SQLAlchemy pool hand a later call a
    connection still bound to an earlier call's now-dead loop — the same cross-loop failure this
    session has hit before, just needing more iterations to surface than a one-or-two-call test.
    """
    limit = CATALOG_LIMIT[PlanTier.starter]
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        for i in range(limit):
            response = client.post(
                f"/businesses/{business.id}/dashboard/catalog/products/new",
                data={"name": f"Product {i}", "price_jod": "1"},
                follow_redirects=False,
            )
            assert response.status_code == 303
            await dispose_engines()

        over_limit_response = client.post(
            f"/businesses/{business.id}/dashboard/catalog/products/new",
            data={"name": "One Too Many", "price_jod": "1"},
        )
    assert over_limit_response.status_code == 400
    assert "upgrade" in over_limit_response.text.lower()


async def test_pro_tier_has_no_catalog_limit(client, pro_business):
    limit = CATALOG_LIMIT[PlanTier.starter]
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        # Create one more product than Starter's own limit — Pro must never reject.
        for i in range(limit + 1):
            response = client.post(
                f"/businesses/{pro_business.id}/dashboard/catalog/products/new",
                data={"name": f"Pro Product {i}", "price_jod": "1"},
                follow_redirects=False,
            )
            assert response.status_code == 303
            await dispose_engines()


async def test_edit_product(client, business):
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        client.post(
            f"/businesses/{business.id}/dashboard/catalog/products/new",
            data={"name": "Original", "price_jod": "5"},
            follow_redirects=False,
        )

    await dispose_engines()
    async with get_sessionmaker()() as session:
        doc = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.product,
            )
        )
        doc_id = doc.id
    await dispose_engines()

    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        response = client.post(
            f"/businesses/{business.id}/dashboard/catalog/products/{doc_id}/edit",
            data={"name": "Renamed", "price_jod": "6", "stock_status": "out_of_stock"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    await dispose_engines()
    async with get_sessionmaker()() as session:
        refreshed = await session.get(KnowledgeDocument, doc_id)
        assert refreshed.structured_data["name"] == "Renamed"
        assert refreshed.structured_data["price_jod"] == 6.0
        assert refreshed.structured_data["stock_status"] == "out_of_stock"


async def test_delete_product(client, business):
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        client.post(
            f"/businesses/{business.id}/dashboard/catalog/products/new",
            data={"name": "To Delete", "price_jod": "1"},
            follow_redirects=False,
        )

    await dispose_engines()
    async with get_sessionmaker()() as session:
        doc = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.product,
            )
        )
        doc_id = doc.id
    await dispose_engines()

    response = client.post(
        f"/businesses/{business.id}/dashboard/catalog/products/{doc_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303

    await dispose_engines()
    async with get_sessionmaker()() as session:
        assert await session.get(KnowledgeDocument, doc_id) is None


async def test_create_product_with_image_stores_it(client, business):
    """Doc 3 roadmap ("agent can send photo samples")."""
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        response = client.post(
            f"/businesses/{business.id}/dashboard/catalog/products/new",
            data={"name": "Photographed Mug", "price_jod": "4"},
            files={"image": ("mug.png", b"fake-png-bytes", "image/png")},
            follow_redirects=False,
        )

    assert response.status_code == 303

    await dispose_engines()
    async with get_sessionmaker()() as session:
        doc = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.product,
            )
        )
        image = await session.scalar(select(ProductImage).where(ProductImage.document_id == doc.id))
        assert image is not None
        assert image.image_data == b"fake-png-bytes"
        assert image.content_type == "image/png"


async def test_create_product_without_image_stores_none(client, business):
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        client.post(
            f"/businesses/{business.id}/dashboard/catalog/products/new",
            data={"name": "No Photo Yet", "price_jod": "2"},
            follow_redirects=False,
        )

    await dispose_engines()
    async with get_sessionmaker()() as session:
        doc = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.product,
            )
        )
        image = await session.scalar(select(ProductImage).where(ProductImage.document_id == doc.id))
        assert image is None


async def test_edit_product_can_add_an_image_later(client, business):
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        client.post(
            f"/businesses/{business.id}/dashboard/catalog/products/new",
            data={"name": "Plain For Now", "price_jod": "3"},
            follow_redirects=False,
        )

    await dispose_engines()
    async with get_sessionmaker()() as session:
        doc = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.product,
            )
        )
        doc_id = doc.id
    await dispose_engines()

    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        client.post(
            f"/businesses/{business.id}/dashboard/catalog/products/{doc_id}/edit",
            data={"name": "Plain For Now", "price_jod": "3"},
            files={"image": ("added.jpg", b"added-later", "image/jpeg")},
            follow_redirects=False,
        )

    await dispose_engines()
    async with get_sessionmaker()() as session:
        image = await session.scalar(select(ProductImage).where(ProductImage.document_id == doc_id))
        assert image is not None
        assert image.image_data == b"added-later"


async def test_edit_product_without_new_image_keeps_the_existing_one(client, business):
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        client.post(
            f"/businesses/{business.id}/dashboard/catalog/products/new",
            data={"name": "Has A Photo", "price_jod": "3"},
            files={"image": ("original.jpg", b"original-bytes", "image/jpeg")},
            follow_redirects=False,
        )

    await dispose_engines()
    async with get_sessionmaker()() as session:
        doc = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.product,
            )
        )
        doc_id = doc.id
    await dispose_engines()

    # Edit without touching the "image" field at all — the existing photo must survive.
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        client.post(
            f"/businesses/{business.id}/dashboard/catalog/products/{doc_id}/edit",
            data={"name": "Has A Photo, Renamed", "price_jod": "3"},
            follow_redirects=False,
        )

    await dispose_engines()
    async with get_sessionmaker()() as session:
        image = await session.scalar(select(ProductImage).where(ProductImage.document_id == doc_id))
        assert image is not None
        assert image.image_data == b"original-bytes"


async def test_edit_product_404s_for_unknown_document(client, business):
    response = client.post(
        f"/businesses/{business.id}/dashboard/catalog/products/{uuid.uuid4()}/edit",
        data={"name": "X", "price_jod": "1"},
    )
    assert response.status_code == 404


async def test_edit_product_404s_for_wrong_type(client, business):
    async with get_sessionmaker()() as session:
        promo_doc = KnowledgeDocument(
            business_id=business.id,
            type=KnowledgeDocType.promotion,
            content="Promotion: X",
            structured_data={"title": "X", "discount_text": "10%"},
        )
        session.add(promo_doc)
        await session.commit()
        await session.refresh(promo_doc)
        doc_id = promo_doc.id
    await dispose_engines()

    response = client.post(
        f"/businesses/{business.id}/dashboard/catalog/products/{doc_id}/edit",
        data={"name": "X", "price_jod": "1"},
    )
    assert response.status_code == 404


# --- Promotions ------------------------------------------------------------------------------


async def test_create_promotion(client, business):
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        response = client.post(
            f"/businesses/{business.id}/dashboard/catalog/promotions/new",
            data={
                "title": "Ramadan Sale",
                "description": "",
                "discount_text": "15% off",
                "applies_to": "",
                "starts_at": "2026-09-01T09:00",
                "ends_at": "2026-09-10T21:00",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    await dispose_engines()
    async with get_sessionmaker()() as session:
        doc = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.promotion,
            )
        )
        assert doc is not None
        assert doc.structured_data["title"] == "Ramadan Sale"
        assert doc.active_from is not None
        assert doc.active_until is not None
        assert doc.embedding_vector is not None


async def test_create_promotion_rejects_ends_before_starts(client, business):
    response = client.post(
        f"/businesses/{business.id}/dashboard/catalog/promotions/new",
        data={
            "title": "Bad window",
            "discount_text": "10% off",
            "starts_at": "2026-09-10T09:00",
            "ends_at": "2026-09-01T09:00",
        },
    )
    assert response.status_code == 400


async def test_edit_promotion(client, business):
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        client.post(
            f"/businesses/{business.id}/dashboard/catalog/promotions/new",
            data={
                "title": "Original",
                "discount_text": "5% off",
                "starts_at": "2026-09-01T09:00",
                "ends_at": "2026-09-10T21:00",
            },
            follow_redirects=False,
        )

    await dispose_engines()
    async with get_sessionmaker()() as session:
        doc = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.promotion,
            )
        )
        doc_id = doc.id
    await dispose_engines()

    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        response = client.post(
            f"/businesses/{business.id}/dashboard/catalog/promotions/{doc_id}/edit",
            data={
                "title": "Updated",
                "discount_text": "25% off",
                "starts_at": "2026-09-02T09:00",
                "ends_at": "2026-09-11T21:00",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    await dispose_engines()
    async with get_sessionmaker()() as session:
        refreshed = await session.get(KnowledgeDocument, doc_id)
        assert refreshed.structured_data["title"] == "Updated"
        assert refreshed.structured_data["discount_text"] == "25% off"


async def test_delete_promotion(client, business):
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        client.post(
            f"/businesses/{business.id}/dashboard/catalog/promotions/new",
            data={
                "title": "To Delete",
                "discount_text": "5% off",
                "starts_at": "2026-09-01T09:00",
                "ends_at": "2026-09-10T21:00",
            },
            follow_redirects=False,
        )

    await dispose_engines()
    async with get_sessionmaker()() as session:
        doc = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.promotion,
            )
        )
        doc_id = doc.id
    await dispose_engines()

    response = client.post(
        f"/businesses/{business.id}/dashboard/catalog/promotions/{doc_id}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303

    await dispose_engines()
    async with get_sessionmaker()() as session:
        assert await session.get(KnowledgeDocument, doc_id) is None


async def test_edit_promotion_404s_for_wrong_type(client, business):
    async with get_sessionmaker()() as session:
        product_doc = KnowledgeDocument(
            business_id=business.id,
            type=KnowledgeDocType.product,
            content="Product: X",
            structured_data={"name": "X", "price_jod": 1, "stock_status": "in_stock"},
        )
        session.add(product_doc)
        await session.commit()
        await session.refresh(product_doc)
        doc_id = product_doc.id
    await dispose_engines()

    response = client.post(
        f"/businesses/{business.id}/dashboard/catalog/promotions/{doc_id}/edit",
        data={
            "title": "X",
            "discount_text": "1%",
            "starts_at": "2026-09-01T09:00",
            "ends_at": "2026-09-02T09:00",
        },
    )
    assert response.status_code == 404


# --- List page --------------------------------------------------------------------------------


async def test_catalog_list_shows_products_and_promotions(client, business):
    # Each TestClient call spins its own event loop (see test_dashboard.py's
    # test_resolve_already_resolved_returns_409 for the same note) — dispose between every
    # pair of calls, not just around raw DB session access.
    with patch(EMBED_PATCH, return_value=[[0.0] * 1024]):
        client.post(
            f"/businesses/{business.id}/dashboard/catalog/products/new",
            data={"name": "Listed Product", "price_jod": "2"},
            follow_redirects=False,
        )
        await dispose_engines()
        client.post(
            f"/businesses/{business.id}/dashboard/catalog/promotions/new",
            data={
                "title": "Listed Promo",
                "discount_text": "5% off",
                "starts_at": "2026-09-01T09:00",
                "ends_at": "2026-09-10T21:00",
            },
            follow_redirects=False,
        )
        await dispose_engines()

    response = client.get(f"/businesses/{business.id}/dashboard/catalog")
    assert response.status_code == 200
    assert "Listed Product" in response.text
    assert "Listed Promo" in response.text


async def test_catalog_list_404s_for_unknown_business(client, business):
    response = client.get("/businesses/00000000-0000-0000-0000-000000000000/dashboard/catalog")
    assert response.status_code == 404
