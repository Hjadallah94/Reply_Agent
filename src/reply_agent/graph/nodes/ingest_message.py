"""Deterministic normalization. Channel-specific parsing (WhatsApp webhook shape, etc.)
already happened before the graph was invoked (see channels/whatsapp/webhook.py) — by the
time a message reaches the graph it's already the internal InboundMessage shape and the
customer/conversation rows already exist (graph/context_resolution.py). This node just
establishes the per-run counters the rest of the graph relies on.
"""

from reply_agent.graph.state import GraphState


async def ingest_message(state: GraphState) -> dict:
    return {"retrieval_attempts": 0}
