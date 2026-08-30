"""Owner-correction feedback loop (Doc 1 Section 7: "Every owner correction on an escalated
draft is captured and folds back into the knowledge base / few-shot examples — the agent gets
better at this specific seller's voice without any model fine-tuning or retraining cost.").

When an owner sends something different from the agent's own drafted reply while resolving an
escalation (api/dashboard.py's resolve_escalation), that pair is captured as a new
brand_voice-type KnowledgeDocument — the exact same few-shot mechanism generate_response.py
already uses for hand-authored brand voice samples (knowledge/loader.py's
sync_knowledge_base) — so it starts influencing future replies to this business's customers
immediately, no fine-tuning or retraining involved, matching the doc's explicit claim.

Deliberately not split into a separate "corrections" table or document type: a correction and a
hand-written brand voice sample are used identically by generate_response.py (a customer/seller
pair shown as a few-shot tone example), so storing them the same way means one query and one
prompt-building path handles both, rather than two mechanisms doing the same job.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from reply_agent.db.models import KnowledgeDocType, KnowledgeDocument
from reply_agent.knowledge.embeddings import embed_documents


async def record_owner_correction(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    customer_message: str,
    corrected_reply: str,
    escalation_id: uuid.UUID | None = None,
    approval_id: uuid.UUID | None = None,
) -> None:
    content = f"Customer: {customer_message}\nSeller: {corrected_reply}"
    vector = embed_documents([content])[0]
    # Same mechanism, two possible triggers (api/dashboard.py's resolve_escalation and
    # approve_approval) — exactly one of these is set depending on which route called this.
    structured_data = {"source": "owner_correction"}
    if escalation_id is not None:
        structured_data["escalation_id"] = str(escalation_id)
    if approval_id is not None:
        structured_data["approval_id"] = str(approval_id)
    session.add(
        KnowledgeDocument(
            business_id=business_id,
            type=KnowledgeDocType.brand_voice,
            content=content,
            # Not used by any query today — generate_response.py's brand_voice lookup is an
            # unfiltered, ordered LIMIT, not a search — but cheap to keep for the first time
            # someone needs to tell a real correction apart from a hand-authored sample (a
            # future "review what your agent has learned" UI, or debugging a bad reply).
            structured_data=structured_data,
            embedding_vector=vector,
        )
    )
