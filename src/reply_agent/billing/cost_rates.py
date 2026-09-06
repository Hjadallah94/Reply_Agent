"""Real per-call cost rates for Doc 5's margin-verification roadmap — "pricing as code" for
third-party API costs, same pattern as tiers.py's TIER_PRICE_JOD/MESSAGE_CAPS. Used by
billing/cost_tracking.py to compute ApiCallLog.cost_usd at write time (not later, at report
time) — a future rate change here must never silently rewrite what a past conversation was
actually estimated to cost.

Keep in sync with md/05_Pricing_Unit_Economics.md's Section 3.3 (Claude rates) if they change.
"""

from reply_agent.llm.client import MODEL_HAIKU, MODEL_SONNET

# Anthropic — same figures already in 05_Pricing_Unit_Economics.md Section 3.3 (Sonnet 5's
# standard rate since its introductory $2/$10 pricing expired August 31, 2026).
CLAUDE_RATES_PER_MILLION_TOKENS_USD: dict[str, dict[str, float]] = {
    MODEL_HAIKU: {"input": 1.00, "output": 5.00},
    MODEL_SONNET: {"input": 3.00, "output": 15.00},
}

# Voyage-3.5 embeddings — https://docs.voyageai.com/docs/pricing (checked 2026-09-06).
VOYAGE_RATE_PER_MILLION_TOKENS_USD = 0.06

# Google Routes API, Compute Route Matrix (integrations/google_maps.py) — our call uses
# routingPreference=TRAFFIC_AWARE, which bills under the "Compute Route Matrix Pro" SKU, not
# the cheaper Essentials tier (TRAFFIC_UNAWARE only). $10.00 per 1,000 elements at the first
# paid tier (5,001-100,000 elements/month) — 1 element = 1 origin x 1 destination = 1 call
# here. A 5,000-element/month free cap also applies but isn't tracked against here; this is a
# marginal per-call estimate, not a monthly-usage-aware exact bill.
# https://developers.google.com/maps/documentation/routes/usage-and-billing
# https://developers.google.com/maps/billing-and-pricing/pricing (checked 2026-09-06)
# Doc 5 Section 3.5 previously left this line item entirely unpriced — first real number.
GOOGLE_MAPS_COST_PER_CALL_USD = 0.01


def claude_call_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = CLAUDE_RATES_PER_MILLION_TOKENS_USD.get(model)
    if rates is None:
        raise ValueError(f"No cost rate configured for Claude model {model!r}")
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


def voyage_call_cost_usd(token_count: int) -> float:
    return token_count * VOYAGE_RATE_PER_MILLION_TOKENS_USD / 1_000_000
