"""Catalog upload endpoint (Doc 3 Phase 2). No owner dashboard UI calls this yet (would be a
natural Phase 3 addition to api/dashboard.py) — for now it's the API half of the ingestion
pipeline, ready for that UI. The CLI (scripts/ingest_catalog.py) uses the same
parse_catalog_workbook/sync_knowledge_base pair. Gated by auth/dependencies.py like the rest
of the per-business surface.
"""

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from reply_agent.auth.dependencies import require_business_access
from reply_agent.db.models import Business
from reply_agent.db.tenant_session import tenant_session
from reply_agent.knowledge.loader import sync_knowledge_base
from reply_agent.knowledge.spreadsheet_ingest import WorkbookParseError, parse_catalog_workbook

router = APIRouter(prefix="/businesses", tags=["knowledge"])


@router.post("/{business_id}/knowledge/upload")
async def upload_catalog(
    file: UploadFile, business: Business = Depends(require_business_access)
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Expected a .xlsx workbook")

    async with tenant_session(business.id) as session:
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
