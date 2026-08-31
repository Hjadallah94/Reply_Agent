"""Single-item catalog CRUD (Doc 3 Phase 6.5) — distinct from knowledge/loader.py's
sync_knowledge_base, which wipes and rebuilds a business's entire product/policy/faq set at
once (right for a bulk spreadsheet re-upload, wrong for editing one product). These functions
create or update exactly one knowledge_documents row, embedding only that row's text — used by
api/dashboard.py's catalog routes, never by the bulk upload path.

No commit inside these functions, same convention as sync_knowledge_base — the caller's
tenant_session block owns the transaction.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from reply_agent.db.models import KnowledgeDocType, KnowledgeDocument
from reply_agent.knowledge.embeddings import embed_documents
from reply_agent.knowledge.schema import Product, Promotion


def _product_structured_data(product: Product) -> dict:
    return {
        "name": product.name,
        "price_jod": product.price_jod,
        "stock_status": product.stock_status,
        "variants": [v.model_dump() for v in product.variants],
    }


async def create_product(
    session: AsyncSession, business_id: uuid.UUID, product: Product
) -> KnowledgeDocument:
    text = product.to_text()
    vector = embed_documents([text])[0]
    document = KnowledgeDocument(
        business_id=business_id,
        type=KnowledgeDocType.product,
        content=text,
        structured_data=_product_structured_data(product),
        embedding_vector=vector,
    )
    session.add(document)
    return document


async def update_product(document: KnowledgeDocument, product: Product) -> None:
    text = product.to_text()
    document.content = text
    document.structured_data = _product_structured_data(product)
    document.embedding_vector = embed_documents([text])[0]


def _promotion_structured_data(promotion: Promotion) -> dict:
    return {
        "title": promotion.title,
        "description": promotion.description,
        "discount_text": promotion.discount_text,
        "applies_to": promotion.applies_to,
    }


async def create_promotion(
    session: AsyncSession, business_id: uuid.UUID, promotion: Promotion
) -> KnowledgeDocument:
    text = promotion.to_text()
    vector = embed_documents([text])[0]
    document = KnowledgeDocument(
        business_id=business_id,
        type=KnowledgeDocType.promotion,
        content=text,
        structured_data=_promotion_structured_data(promotion),
        embedding_vector=vector,
        active_from=promotion.starts_at,
        active_until=promotion.ends_at,
    )
    session.add(document)
    return document


async def update_promotion(document: KnowledgeDocument, promotion: Promotion) -> None:
    text = promotion.to_text()
    document.content = text
    document.structured_data = _promotion_structured_data(promotion)
    document.embedding_vector = embed_documents([text])[0]
    document.active_from = promotion.starts_at
    document.active_until = promotion.ends_at
