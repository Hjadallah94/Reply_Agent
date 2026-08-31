"""Loads a business's manually-entered knowledge base (Phase 1 stub) from YAML files
and syncs it into knowledge_documents. Phase 2 replaces the *source* (spreadsheet/doc
upload) but should call the same sync_knowledge_base() with a KnowledgeBase it builds
from the ingestion pipeline instead of from disk.
"""

from pathlib import Path

import yaml
from sqlalchemy import and_, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from reply_agent.db.models import KnowledgeDocType, KnowledgeDocument
from reply_agent.knowledge.embeddings import embed_documents
from reply_agent.knowledge.schema import BrandVoiceSample, FAQPair, KnowledgeBase, Policy, Product

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "knowledge_base"


def load_knowledge_base(business_slug: str) -> KnowledgeBase:
    business_dir = DATA_DIR / business_slug
    if not business_dir.is_dir():
        raise FileNotFoundError(
            f"No knowledge base directory for '{business_slug}' at {business_dir}"
        )

    def _read(name: str) -> list[dict]:
        path = business_dir / name
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or []

    return KnowledgeBase(
        business_slug=business_slug,
        products=[Product(**p) for p in _read("catalog.yaml")],
        policies=[Policy(**p) for p in _read("policies.yaml")],
        faqs=[FAQPair(**p) for p in _read("faqs.yaml")],
        brand_voice_samples=[BrandVoiceSample(**p) for p in _read("brand_voice.yaml")],
    )


async def sync_knowledge_base(session: AsyncSession, business_id, kb: KnowledgeBase) -> int:
    """Replaces all product/policy/faq/brand_voice knowledge_documents rows for this business
    with the given KnowledgeBase. Returns the number of documents written. Doesn't commit — the
    caller owns the transaction (a plain script commits once at the end; api/knowledge.py's
    tenant_session commits on its own block exit, and committing here too would end that
    transaction early).

    The delete below is deliberately narrower than "everything for this business": product/
    policy/faq rows always go (a KnowledgeBase always fully replaces those), and brand_voice
    rows go *unless* they carry knowledge/corrections.py's owner-correction marker
    (structured_data.source == "owner_correction"). Two real, previously-silent bugs this
    fixes: parse_catalog_workbook never populates brand_voice_samples (no such sheet in a
    spreadsheet upload), so a blanket delete would wipe every owner-correction sample on the
    next spreadsheet re-upload even though the upload never meant to touch them; a blanket
    delete would also wipe any promotion (knowledge/catalog.py, dashboard-only, Doc 3 Phase
    6.5) a business created, which promotion rows never being product/policy/faq/brand_voice
    with that marker already keeps out of this delete. YAML-sourced brand_voice samples (no
    marker) still get replaced on each call, same as before — scripts/seed_business.py stays
    idempotent across re-runs.
    """
    await session.execute(
        delete(KnowledgeDocument).where(
            KnowledgeDocument.business_id == business_id,
            or_(
                KnowledgeDocument.type.in_(
                    [KnowledgeDocType.product, KnowledgeDocType.policy, KnowledgeDocType.faq]
                ),
                and_(
                    KnowledgeDocument.type == KnowledgeDocType.brand_voice,
                    func.coalesce(KnowledgeDocument.structured_data["source"].astext, "")
                    != "owner_correction",
                ),
            ),
        )
    )

    entries: list[tuple[KnowledgeDocType, str, dict]] = []
    for product in kb.products:
        entries.append(
            (
                KnowledgeDocType.product,
                product.to_text(),
                {
                    "name": product.name,
                    "price_jod": product.price_jod,
                    "stock_status": product.stock_status,
                    "variants": [v.model_dump() for v in product.variants],
                },
            )
        )
    for policy in kb.policies:
        entries.append((KnowledgeDocType.policy, policy.to_text(), {"topic": policy.topic}))
    for faq in kb.faqs:
        entries.append((KnowledgeDocType.faq, faq.to_text(), {"question": faq.question}))
    for sample in kb.brand_voice_samples:
        entries.append(
            (
                KnowledgeDocType.brand_voice,
                f"Customer: {sample.customer_message}\nSeller: {sample.seller_reply}",
                {},
            )
        )

    if not entries:
        return 0

    vectors = embed_documents([text for _, text, _ in entries])
    for (doc_type, text, structured_data), vector in zip(entries, vectors, strict=True):
        session.add(
            KnowledgeDocument(
                business_id=business_id,
                type=doc_type,
                content=text,
                structured_data=structured_data,
                embedding_vector=vector,
            )
        )

    return len(entries)
