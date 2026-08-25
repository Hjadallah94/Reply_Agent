"""Hybrid RAG (Doc 2 Section 2.2): a vector similarity search over knowledge_documents, plus
an exact order lookup (Doc 2 Section 2.6) when the question is actually about an order.
Structured lookups for price/stock aren't a separate query in this Phase 1/2 stub — the loader
embeds the structured catalog fields directly into each chunk's text (Doc 2 says precision
matters more than recall for price/stock; the catalog is small enough per tenant that this
stays accurate). Orders are different: they change constantly and must never be guessed from a
vector match, so they get a real exact-match query instead.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reply_agent.db.models import Customer, KnowledgeDocType, KnowledgeDocument, Order
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.state import GraphState
from reply_agent.knowledge.embeddings import embed_query

TOP_K = 5
ORDER_LOOKUP_LIMIT = 3


async def _find_order_context(session: AsyncSession, state: GraphState) -> list[dict]:
    """Only looked up for order_status questions, and only WhatsApp customers are phone-
    identified (Instagram/Messenger customer_handle is an opaque IGSID/PSID, not a phone
    number, so it can't match a seller's order sheet) — see orders/phone.py.
    """
    intent = state.get("intent")
    if not intent or intent["label"] != "order_status" or state["channel"] != "whatsapp":
        return []

    customer = await session.get(Customer, uuid.UUID(state["customer_id"]))
    if customer is None:
        return []

    orders = (
        await session.scalars(
            select(Order)
            .where(
                Order.business_id == uuid.UUID(state["business_id"]),
                Order.customer_phone == customer.channel_handle,
            )
            .order_by(Order.order_date.desc().nulls_last())
            .limit(ORDER_LOOKUP_LIMIT)
        )
    ).all()

    context = []
    for order in orders:
        snippet = f"Order {order.order_reference}: status={order.status}"
        if order.items_summary:
            snippet += f", items={order.items_summary}"
        if order.order_date:
            snippet += f", date={order.order_date.date().isoformat()}"
        context.append({"source": f"order:{order.id}", "snippet": snippet, "score": 1.0})
    return context


async def retrieve_knowledge(state: GraphState) -> dict:
    query_vector = embed_query(state["message"]["text"])

    async with tenant_session(uuid.UUID(state["business_id"])) as session:
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

        order_context = await _find_order_context(session, state)

    retrieved_context = order_context + [
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
