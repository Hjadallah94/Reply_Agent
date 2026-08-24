"""Catalog upload endpoint (Doc 3 Phase 2). No owner dashboard exists yet (Phase 3) — this is
the API half of the ingestion pipeline, ready for that dashboard to call once it exists. The
CLI (scripts/ingest_catalog.py) uses the same parse_catalog_workbook/sync_knowledge_base pair.
"""

import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from reply_agent.db.models import Business
from reply_agent.db.session import get_sessionmaker
from reply_agent.knowledge.loader import sync_knowledge_base
from reply_agent.knowledge.spreadsheet_ingest import WorkbookParseError, parse_catalog_workbook

router = APIRouter(prefix="/businesses", tags=["knowledge"])


@router.post("/{business_id}/knowledge/upload")
async def upload_catalog(business_id: uuid.UUID, file: UploadFile) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Expected a .xlsx workbook")

    async with get_sessionmaker()() as session:
        business = await session.get(Business, business_id)
        if business is None:
            raise HTTPException(status_code=404, detail="Business not found")

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)

        try:
            kb, issues = parse_catalog_workbook(str(tmp_path), business_slug=business.name)
        except WorkbookParseError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        finally:
            tmp_path.unlink(missing_ok=True)

        doc_count = await sync_knowledge_base(session, business.id, kb)

    return {
        "products": len(kb.products),
        "policies": len(kb.policies),
        "faqs": len(kb.faqs),
        "documents_embedded": doc_count,
        "issues": issues,
    }
