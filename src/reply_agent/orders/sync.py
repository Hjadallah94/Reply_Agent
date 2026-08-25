"""Upserts parsed order records (orders/spreadsheet_ingest.py) — replaces the whole set per
business on each sync (a full re-sync is simple and correct for a spreadsheet fallback; a
seller re-exports/re-uploads their sheet rather than us tracking incremental diffs), mirroring
knowledge/loader.py's sync_knowledge_base. No embeddings involved — orders are looked up by
exact phone match (graph/nodes/retrieve_knowledge.py), not vector similarity.

Doesn't commit — the caller owns the transaction, same reasoning as sync_knowledge_base.
"""

import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from reply_agent.db.models import Order
from reply_agent.orders.schema import OrderRecord


async def sync_orders(
    session: AsyncSession, business_id: uuid.UUID, records: list[OrderRecord]
) -> int:
    await session.execute(delete(Order).where(Order.business_id == business_id))

    for record in records:
        session.add(
            Order(
                business_id=business_id,
                order_reference=record.order_reference,
                customer_phone=record.customer_phone,
                customer_name=record.customer_name,
                status=record.status,
                items_summary=record.items_summary,
                order_date=record.order_date,
            )
        )

    return len(records)
