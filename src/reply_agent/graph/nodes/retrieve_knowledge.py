"""Hybrid RAG (Doc 2 Section 2.2): a single vector similarity search over knowledge_documents.
Structured lookups (exact price/stock) aren't a separate query in this Phase 1 stub — the
loader embeds the structured catalog fields directly into each chunk's text (Doc 2 says
precision matters more than recall for price/stock; the catalog is small enough per tenant
that this stays accurate). A real structured-lookup path is a natural Phase 2/3 addition once
storefront integrations (Doc 2 Section 2.6) give us a live table to query.
"""

import uuid

from sqlalchemy import select

from reply_agent.db.models import KnowledgeDocType, KnowledgeDocument
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.state import GraphState
from reply_agent.knowledge.embeddings import embed_query

TOP_K = 5


async def retrieve_knowledge(state: GraphState) -> dict:
    query_vector = embed_query(state["message"]["text"])

    async with get_sessionmaker()() as session:
        distance = KnowledgeDocument.embedding_vector.cosine_distance(query_vector)
        rows = (
            await session.execute(
                select(KnowledgeDocument, distance.label("distance"))
                .where(
                    KnowledgeDocument.business_id == uuid.UUID(state["business_id"]),
                    # brand_voice docs are style examples for generate_response's few-shot
                    # prompt (queried separately there) — never factual grounding. Retrieving
                    # them here lets self_check mistake example dialogue for real conversation
                    # history/stock data.
                    KnowledgeDocument.type != KnowledgeDocType.brand_voice,
                )
                .order_by(distance)
                .limit(TOP_K)
            )
        ).all()

    retrieved_context = [
        {
            "source": str(doc.id),
            "snippet": doc.content,
            "score": 1.0 - float(distance),
        }
        for doc, distance in rows
    ]

    return {
        "retrieved_context": retrieved_context,
        "retrieval_attempts": state.get("retrieval_attempts", 0) + 1,
    }
