"""Real DB, mocked embeddings — CI has Postgres (migrations run first) but no Voyage/Anthropic
keys, so sync_knowledge_base (which calls out to Voyage) is the one thing mocked here. Gated by
auth/dependencies.py — tests log in via tests/auth_helpers.py.
"""

import io
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import delete, select

from reply_agent.api.app import app
from reply_agent.db.models import Business, KnowledgeDocType, KnowledgeDocument
from reply_agent.db.session import get_sessionmaker
from tests.auth_helpers import create_logged_in_business, dispose_engines

BUSINESS_NAME = "Knowledge Upload Test Business"


def _workbook_bytes() -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    products = wb.create_sheet("Products")
    products.append(["name", "price_jod"])
    products.append(["Test Abaya", 30])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
async def business(client):
    b = await create_logged_in_business(client, BUSINESS_NAME)
    yield b
    # The test body made its own TestClient calls after create_logged_in_business's own
    # dispose — same cross-loop issue, dispose again before this fixture's own DB access.
    await dispose_engines()
    async with get_sessionmaker()() as session:
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


async def test_upload_rejects_non_xlsx(client, business):
    response = client.post(
        f"/businesses/{business.id}/knowledge/upload",
        files={"file": ("catalog.csv", b"name,price_jod\nAbaya,30", "text/csv")},
    )
    assert response.status_code == 400


async def test_upload_404s_for_unknown_business(client, business):
    response = client.post(
        "/businesses/00000000-0000-0000-0000-000000000000/knowledge/upload",
        files={"file": ("catalog.xlsx", _workbook_bytes(), "application/octet-stream")},
    )
    assert response.status_code == 404


async def test_upload_parses_and_syncs(client, business):
    with patch(
        "reply_agent.api.knowledge.sync_knowledge_base", new=AsyncMock(return_value=1)
    ) as mock_sync:
        response = client.post(
            f"/businesses/{business.id}/knowledge/upload",
            files={"file": ("catalog.xlsx", _workbook_bytes(), "application/octet-stream")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["products"] == 1
    assert body["documents_embedded"] == 1
    assert body["issues"] == []
    mock_sync.assert_called_once()


async def test_upload_does_not_wipe_owner_corrections_or_promotions(client, business):
    """Real bug found while building Phase 6e: an unscoped delete in sync_knowledge_base would
    silently wipe brand-voice corrections (parse_catalog_workbook never populates
    brand_voice_samples) and dashboard-created promotions on every spreadsheet re-upload.
    """
    async with get_sessionmaker()() as session:
        session.add(
            KnowledgeDocument(
                id=uuid.uuid4(),
                business_id=business.id,
                type=KnowledgeDocType.brand_voice,
                content="Customer: hi\nSeller: hello!",
                structured_data={"source": "owner_correction", "escalation_id": "abc"},
            )
        )
        session.add(
            KnowledgeDocument(
                id=uuid.uuid4(),
                business_id=business.id,
                type=KnowledgeDocType.promotion,
                content="Promotion: Sale",
                structured_data={"title": "Sale", "discount_text": "10% off"},
                active_from=datetime.now(UTC) - timedelta(days=1),
                active_until=datetime.now(UTC) + timedelta(days=6),
            )
        )
        await session.commit()
    await dispose_engines()

    with patch(
        "reply_agent.knowledge.loader.embed_documents", return_value=[[0.0] * 1024]
    ):
        response = client.post(
            f"/businesses/{business.id}/knowledge/upload",
            files={"file": ("catalog.xlsx", _workbook_bytes(), "application/octet-stream")},
        )

    assert response.status_code == 200
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

        promotion = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.promotion,
            )
        )
        assert promotion is not None

        product = await session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.business_id == business.id,
                KnowledgeDocument.type == KnowledgeDocType.product,
            )
        )
        assert product is not None
        assert product.structured_data["name"] == "Test Abaya"
