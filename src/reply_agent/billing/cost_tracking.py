"""Doc 5 margin-verification roadmap — writes one ApiCallLog row per third-party API call a
graph node makes, so scripts/conversation_cost_report.py can total up exactly what one
conversation actually cost. None of these commit — same convention as every other write
helper in this codebase (knowledge/catalog.py, orders/sync.py, ...): the caller's already-open
tenant_session owns the transaction.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from reply_agent.billing.cost_rates import (
    GOOGLE_MAPS_COST_PER_CALL_USD,
    claude_call_cost_usd,
    voyage_call_cost_usd,
)
from reply_agent.db.models import ApiCallLog, ApiCallProvider

# Voyage's Python client doesn't reliably surface exact token usage through embed_query's
# current single-value return shape (knowledge/embeddings.py), and this cost line is negligible
# next to the Claude calls that actually dominate a conversation's cost — a simple ~4-chars/
# token estimate is good enough here specifically, not a stand-in for precise LLM token counts.
_CHARS_PER_TOKEN_ESTIMATE = 4


async def log_anthropic_call(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    thread_id: str,
    node_name: str,
    model: str,
    usage,
) -> None:
    """usage is an Anthropic SDK Usage object (response.usage from messages.create/.parse) —
    duck-typed on .input_tokens/.output_tokens rather than imported as a type, so this has no
    hard dependency on the anthropic package's internal class layout.
    """
    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens
    session.add(
        ApiCallLog(
            business_id=business_id,
            thread_id=thread_id,
            node_name=node_name,
            provider=ApiCallProvider.anthropic,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=claude_call_cost_usd(model, input_tokens, output_tokens),
        )
    )


async def log_google_maps_call(
    session: AsyncSession, *, business_id: uuid.UUID, thread_id: str, node_name: str
) -> None:
    """One row per estimate_transit_minutes call (integrations/google_maps.py) — always
    exactly 1 origin x 1 destination = 1 "element" the way this app calls the Routes API.
    """
    session.add(
        ApiCallLog(
            business_id=business_id,
            thread_id=thread_id,
            node_name=node_name,
            provider=ApiCallProvider.google_maps,
            model="routes_compute_route_matrix",
            units=1,
            cost_usd=GOOGLE_MAPS_COST_PER_CALL_USD,
        )
    )


async def log_voyage_call(
    session: AsyncSession, *, business_id: uuid.UUID, thread_id: str, node_name: str, text: str
) -> None:
    """One row per embed_query call (knowledge/embeddings.py) — token count is an estimate,
    see the module docstring above."""
    estimated_tokens = max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)
    session.add(
        ApiCallLog(
            business_id=business_id,
            thread_id=thread_id,
            node_name=node_name,
            provider=ApiCallProvider.voyage,
            model="voyage-3.5",
            input_tokens=estimated_tokens,
            cost_usd=voyage_call_cost_usd(estimated_tokens),
        )
    )
