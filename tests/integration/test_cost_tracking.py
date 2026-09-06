"""billing/cost_tracking.py — Doc 5 margin-verification roadmap. Real DB (tenant_session),
no external API calls: log_anthropic_call is duck-typed on a .input_tokens/.output_tokens
usage object, so a plain stand-in (not the real Anthropic SDK class) is enough here.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from reply_agent.billing.cost_tracking import (
    log_anthropic_call,
    log_google_maps_call,
    log_voyage_call,
)
from reply_agent.db.models import ApiCallLog, ApiCallProvider, Business, PlanTier
from reply_agent.db.session import get_sessionmaker
from reply_agent.db.tenant_session import tenant_session
from reply_agent.llm.client import MODEL_HAIKU, MODEL_SONNET

THREAD_ID = "whatsapp:business:962790001234"


@pytest.fixture
async def business():
    async with get_sessionmaker()() as session:
        b = Business(name="Cost Tracking Test Business", plan_tier=PlanTier.starter)
        session.add(b)
        await session.commit()
        await session.refresh(b)
        yield b
        await session.execute(delete(ApiCallLog).where(ApiCallLog.business_id == b.id))
        await session.execute(delete(Business).where(Business.id == b.id))
        await session.commit()


async def _logs_for(business_id) -> list[ApiCallLog]:
    async with get_sessionmaker()() as session:
        return list(
            (
                await session.scalars(
                    select(ApiCallLog).where(ApiCallLog.business_id == business_id)
                )
            ).all()
        )


async def test_log_anthropic_call_computes_haiku_cost(business):
    usage = SimpleNamespace(input_tokens=1000, output_tokens=200)
    async with tenant_session(business.id) as session:
        await log_anthropic_call(
            session,
            business_id=business.id,
            thread_id=THREAD_ID,
            node_name="classify_intent",
            model=MODEL_HAIKU,
            usage=usage,
        )

    logs = await _logs_for(business.id)
    assert len(logs) == 1
    log = logs[0]
    assert log.provider == ApiCallProvider.anthropic
    assert log.model == MODEL_HAIKU
    assert log.input_tokens == 1000
    assert log.output_tokens == 200
    # (1000 * $1.00 + 200 * $5.00) / 1,000,000
    assert float(log.cost_usd) == pytest.approx(0.002)


async def test_log_anthropic_call_computes_sonnet_cost(business):
    usage = SimpleNamespace(input_tokens=2000, output_tokens=500)
    async with tenant_session(business.id) as session:
        await log_anthropic_call(
            session,
            business_id=business.id,
            thread_id=THREAD_ID,
            node_name="generate_response",
            model=MODEL_SONNET,
            usage=usage,
        )

    logs = await _logs_for(business.id)
    assert len(logs) == 1
    # (2000 * $3.00 + 500 * $15.00) / 1,000,000
    assert float(logs[0].cost_usd) == pytest.approx(0.0135)


async def test_log_google_maps_call_flat_rate(business):
    async with tenant_session(business.id) as session:
        await log_google_maps_call(
            session,
            business_id=business.id,
            thread_id=THREAD_ID,
            node_name="estimate_delivery.transit_minutes",
        )

    logs = await _logs_for(business.id)
    assert len(logs) == 1
    log = logs[0]
    assert log.provider == ApiCallProvider.google_maps
    assert log.units == 1
    assert log.input_tokens is None
    assert float(log.cost_usd) == pytest.approx(0.01)


async def test_log_voyage_call_estimates_tokens_from_text(business):
    async with tenant_session(business.id) as session:
        await log_voyage_call(
            session,
            business_id=business.id,
            thread_id=THREAD_ID,
            node_name="retrieve_knowledge.embed_query",
            text="a" * 400,  # ~100 estimated tokens at 4 chars/token
        )

    logs = await _logs_for(business.id)
    assert len(logs) == 1
    log = logs[0]
    assert log.provider == ApiCallProvider.voyage
    assert log.input_tokens == 100
    assert log.cost_usd > 0


async def test_multiple_calls_on_one_thread_all_persist(business):
    """The shape scripts/conversation_cost_report.py relies on — every call across a
    conversation's graph run lands as its own row, filterable by thread_id."""
    async with tenant_session(business.id) as session:
        await log_anthropic_call(
            session,
            business_id=business.id,
            thread_id=THREAD_ID,
            node_name="classify_intent",
            model=MODEL_HAIKU,
            usage=SimpleNamespace(input_tokens=100, output_tokens=20),
        )
        await log_google_maps_call(
            session, business_id=business.id, thread_id=THREAD_ID, node_name="estimate_delivery"
        )

    async with get_sessionmaker()() as session:
        logs = (
            await session.scalars(select(ApiCallLog).where(ApiCallLog.thread_id == THREAD_ID))
        ).all()

    assert {log.provider for log in logs} == {
        ApiCallProvider.anthropic,
        ApiCallProvider.google_maps,
    }
