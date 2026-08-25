"""Real DB, mocked embeddings — CI has Postgres (migrations run first) but no Voyage/Anthropic
keys, so sync_knowledge_base (which calls out to Voyage) is the one thing mocked here. Gated by
auth/dependencies.py — tests log in via tests/auth_helpers.py.
"""

import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import delete

from reply_agent.api.app import app
from reply_agent.db.models import Business
from reply_agent.db.session import get_engine, get_sessionmaker
from tests.auth_helpers import create_logged_in_business

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
    await get_engine().dispose()
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
