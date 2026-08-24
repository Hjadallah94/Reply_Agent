"""Real DB, mocked embeddings — CI has Postgres (migrations run first) but no Voyage/Anthropic
keys, so sync_knowledge_base (which calls out to Voyage) is the one thing mocked here.
"""

import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import delete

from reply_agent.api.app import app
from reply_agent.db.models import Business, PlanTier
from reply_agent.db.session import get_sessionmaker

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
async def business():
    async with get_sessionmaker()() as session:
        b = Business(name=BUSINESS_NAME, plan_tier=PlanTier.starter)
        session.add(b)
        await session.commit()
        await session.refresh(b)
        yield b
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


async def test_upload_rejects_non_xlsx(business):
    client = TestClient(app)
    response = client.post(
        f"/businesses/{business.id}/knowledge/upload",
        files={"file": ("catalog.csv", b"name,price_jod\nAbaya,30", "text/csv")},
    )
    assert response.status_code == 400


async def test_upload_404s_for_unknown_business():
    client = TestClient(app)
    response = client.post(
        "/businesses/00000000-0000-0000-0000-000000000000/knowledge/upload",
        files={"file": ("catalog.xlsx", _workbook_bytes(), "application/octet-stream")},
    )
    assert response.status_code == 404


async def test_upload_parses_and_syncs(business):
    with patch(
        "reply_agent.api.knowledge.sync_knowledge_base", new=AsyncMock(return_value=1)
    ) as mock_sync:
        client = TestClient(app)
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
