"""billing/cost_rates.py — Doc 5 margin-verification roadmap. Pure cost math, no DB/API calls."""

import pytest

from reply_agent.billing.cost_rates import (
    GOOGLE_MAPS_COST_PER_CALL_USD,
    claude_call_cost_usd,
    voyage_call_cost_usd,
)
from reply_agent.llm.client import MODEL_HAIKU, MODEL_SONNET


def test_claude_call_cost_haiku():
    # $1.00/$5.00 per million input/output tokens.
    cost = claude_call_cost_usd(MODEL_HAIKU, input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(6.00)


def test_claude_call_cost_sonnet():
    # $3.00/$15.00 per million input/output tokens.
    cost = claude_call_cost_usd(MODEL_SONNET, input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(18.00)


def test_claude_call_cost_small_call_matches_pricing_doc_ballpark():
    # 05_Pricing_Unit_Economics.md's classify_intent line: Haiku, 200 in / 20 out ~= $0.0003.
    cost = claude_call_cost_usd(MODEL_HAIKU, input_tokens=200, output_tokens=20)
    assert cost == pytest.approx(0.0003, abs=0.00002)


def test_claude_call_cost_rejects_unknown_model():
    with pytest.raises(ValueError, match="claude-opus"):
        claude_call_cost_usd("claude-opus", input_tokens=100, output_tokens=10)


def test_voyage_call_cost():
    # $0.06 per million tokens.
    assert voyage_call_cost_usd(1_000_000) == pytest.approx(0.06)
    assert voyage_call_cost_usd(0) == 0.0


def test_google_maps_cost_per_call_is_a_flat_rate():
    assert GOOGLE_MAPS_COST_PER_CALL_USD == pytest.approx(0.01)
