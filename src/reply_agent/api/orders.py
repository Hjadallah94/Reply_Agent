"""Order sync endpoint (Doc 2 Section 2.6). Same shape as api/knowledge.py's catalog upload —
ready for Phase 3's dashboard, no UI yet. Gated by auth/dependencies.py like the rest of the
per-business surface.
"""

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from reply_agent.auth.dependencies import require_business_access
from reply_agent.db.models import Business
from reply_agent.db.session import get_sessionmaker
from reply_agent.orders.spreadsheet_ingest import OrderWorkbookParseError, parse_orders_workbook
from reply_agent.orders.sync import sync_orders

router = APIRouter(prefix="/businesses", tags=["orders"])


@router.post("/{business_id}/orders/upload")
async def upload_orders(
    file: UploadFile, business: Business = Depends(require_business_access)
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Expected a .xlsx workbook")

    async with get_sessionmaker()() as session:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)

        try:
            records, issues = parse_orders_workbook(str(tmp_path))
        except OrderWorkbookParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            tmp_path.unlink(missing_ok=True)

        count = await sync_orders(session, business.id, records)

    return {"orders_synced": count, "issues": issues}
