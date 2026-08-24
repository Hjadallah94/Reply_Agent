"""Real DB, no embeddings involved (unlike test_knowledge_upload.py) — order sync doesn't
touch Voyage at all, so nothing needs mocking here beyond what conftest.py already handles.
"""

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import delete, select

from reply_agent.api.app import app
from reply_agent.db.models import Business, Order, PlanTier
from reply_agent.db.session import get_engine, get_sessionmaker

BUSINESS_NAME = "Orders Upload Test Business"


def _workbook_bytes() -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    orders = wb.create_sheet("Orders")
    orders.append(["order_reference", "customer_phone", "customer_name", "status"])
    orders.append(["ORD-1", "0791234567", "Sara", "shipped"])
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
        await session.execute(delete(Order).where(Order.business_id == b.id))
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


async def test_upload_rejects_non_xlsx(business):
    client = TestClient(app)
    response = client.post(
        f"/businesses/{business.id}/orders/upload",
        files={"file": ("orders.csv", b"order_reference,customer_phone,status", "text/csv")},
    )
    assert response.status_code == 400


async def test_upload_404s_for_unknown_business():
    client = TestClient(app)
    response = client.post(
        "/businesses/00000000-0000-0000-0000-000000000000/orders/upload",
        files={"file": ("orders.xlsx", _workbook_bytes(), "application/octet-stream")},
    )
    assert response.status_code == 404


async def test_upload_syncs_orders(business):
    client = TestClient(app)
    response = client.post(
        f"/businesses/{business.id}/orders/upload",
        files={"file": ("orders.xlsx", _workbook_bytes(), "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["orders_synced"] == 1
    assert body["issues"] == []

    # TestClient ran the request through its own internal event loop; the connection pool
    # created there breaks if reused from this test's loop (same issue conftest.py's
    # autouse fixture handles between tests — here it's within one test, so dispose explicitly).
    await get_engine().dispose()

    async with get_sessionmaker()() as session:
        order = await session.scalar(select(Order).where(Order.business_id == business.id))
        assert order.order_reference == "ORD-1"
        assert order.customer_phone == "962791234567"
        assert order.status == "shipped"
