"""Genuinely public, unauthenticated routes — deliberately separate from api/dashboard.py
(every one of whose routes goes through require_business_access) so nothing here can ever be
accidentally wrapped in that dependency later.
"""

import uuid

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from reply_agent.db.models import ProductImage
from reply_agent.db.session import get_sessionmaker

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/products/{document_id}/image")
async def product_image(document_id: uuid.UUID) -> Response:
    """Doc 3 roadmap ("agent can send photo samples") — fetched directly by Meta's servers
    when send_reply.py sends a product image by URL (WhatsApp/Instagram/Messenger all send
    media as a link, not an upload), so this can never require a session cookie. Not tenant-
    scoped: the caller has no business context at all, only a document_id — same reasoning as
    graph/context_resolution.py's cross-tenant lookups, so this uses the plain superuser
    session (db/session.py), not tenant_session.
    """
    async with get_sessionmaker()() as session:
        image = await session.scalar(
            select(ProductImage).where(ProductImage.document_id == document_id)
        )

    if image is None:
        raise HTTPException(status_code=404, detail="No image for this product")

    return Response(content=image.image_data, media_type=image.content_type)
