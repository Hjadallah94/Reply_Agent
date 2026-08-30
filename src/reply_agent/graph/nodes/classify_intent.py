from typing import Literal

from pydantic import BaseModel

from reply_agent.graph.state import GraphState
from reply_agent.llm.client import MODEL_HAIKU, get_anthropic_client

IntentLabel = Literal[
    "product_availability_price",
    "place_order",
    "order_status",
    "policy_question",
    "price_negotiation",
    "refund_or_complaint",
    "competitor_mention",
    "legal_threat",
    "spam_or_irrelevant",
    "other",
]


class IntentClassification(BaseModel):
    label: IntentLabel
    confidence: float
    sentiment: Literal["positive", "neutral", "negative"]


CLASSIFY_SYSTEM_PROMPT = """Classify the customer's latest DM to an online seller in Jordan.
label: the single best-fitting category.
confidence: your confidence in that label, 0.0-1.0.
sentiment: the customer's emotional tone in their latest message.

Category guide:
- product_availability_price: asking if something is in stock, what size/color is available, or
  its price — not yet confirming they want to buy it.
- place_order: confirming or requesting to buy specific item(s) now (e.g. "I'll take 2 of the
  chocolate chip cookies", "بدي اطلب"), including when they also give or ask about a delivery
  address/time. Distinct from product_availability_price, which is just asking questions.
- order_status: asking about an order they already placed.
- policy_question: delivery time, payment methods, returns/exchanges.
- price_negotiation: asking for a discount, "best price", or negotiating.
- refund_or_complaint: wants a refund, is complaining about a product/order.
- competitor_mention: compares to or mentions another seller/brand.
- legal_threat: threatens legal action, regulators, or public complaint escalation.
- spam_or_irrelevant: not a genuine customer inquiry.
- other: anything else.
"""


async def classify_intent(state: GraphState) -> dict:
    history_text = "\n".join(
        f"{t['role']}: {t['text']}" for t in state["conversation_history"][-6:]
    )
    user_prompt = (
        f"Conversation so far:\n{history_text}\n\n"
        f"Latest customer message:\n{state['message']['text']}"
    )

    client = get_anthropic_client()
    response = await client.messages.parse(
        model=MODEL_HAIKU,
        max_tokens=256,
        system=CLASSIFY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        output_format=IntentClassification,
    )
    result = response.parsed_output

    return {
        "intent": {
            "label": result.label,
            "confidence": result.confidence,
            "sentiment": result.sentiment,
        }
    }
