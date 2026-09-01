"""The agent's first live-tool-calling capability (Doc 2 Section 9.1): calls Google Maps and
queries the current order backlog mid-conversation, rather than only retrieving pre-embedded
knowledge. Wired via add_edge in graph.py (not a second conditional-edges branch) but
internally no-ops for every intent except place_order — same internal-gating pattern
retrieve_knowledge.py's _find_order_context already uses for order_status, applied
consistently, so graph.py keeps its single linear topology with one conditional-edge fan-out
point at self_check.

min_lead_hours (Business.delivery_rules) is the business's general/default expectation, not a
floor clamped onto every estimate — the live computation below (transit time + today's backlog)
is what actually gets quoted, and can legitimately beat it on a quiet day. Confirmed directly
with the business owner, not assumed: a 6h "usual minimum" and a live 3-4h estimate on a good
day are both correct, not a contradiction.

Doc 3 roadmap (partner meeting 2026-09-01, order confirmation layer): _extract_order_details
now always runs, even past the same-day cutoff — every place_order needs a delivery_address to
create the pending-confirmation Order row below, not just same-day ones. This costs one Haiku
call on a past-cutoff message that used to be entirely free/deterministic; confirmed with the
business owner as worth it (AskUserQuestion) to close the gap where next-day orders previously
auto-sent with zero customer/owner check of any kind.
"""

import uuid
from datetime import datetime, time
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import func, select

from reply_agent.db.models import Business, Customer, Order, OrderConfirmationStatus
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.state import GraphState
from reply_agent.integrations.google_maps import GoogleMapsError, estimate_transit_minutes
from reply_agent.llm.client import MODEL_HAIKU, get_anthropic_client

AMMAN_TZ = ZoneInfo("Asia/Amman")
DEFAULT_CUTOFF_HOUR = 15
DEFAULT_MIN_LEAD_HOURS = 6
# Rough, deliberately simple queueing assumption for this first increment — each already-
# pending delivery today adds this many minutes to a new estimate. Revisit with real pilot
# data once there's any (Doc 2 Section 9.4's adaptive-autonomy data collection is the natural
# home for tuning this later, not a hardcoded guess).
MINUTES_PER_ORDER_IN_QUEUE = 20


class OrderExtraction(BaseModel):
    product_count: int
    delivery_address: str | None = None


def _matches_excluded_location(delivery_address: str, excluded_locations: list[str]) -> bool:
    """Simple case-insensitive substring match, either direction — good enough for free-text
    entries like "Sweifieh - back streets" matching a customer address that mentions either
    the excluded phrase or a shorter version of it (Doc 3 roadmap, partner meeting
    2026-09-01's "a location that the Owner does not send orders to").
    """
    address_lower = delivery_address.lower()
    return any(
        excluded.lower() in address_lower or address_lower in excluded.lower()
        for excluded in excluded_locations
        if excluded.strip()
    )


EXTRACT_SYSTEM_PROMPT = """The customer is placing an order with an online seller in Jordan.
Extract:
- product_count: how many items they're ordering (best guess if not explicit, default 1).
- delivery_address: their delivery address if they stated one in this message, else null.
Only use what's actually in the message — never guess an address that isn't there.
"""


async def _extract_order_details(message_text: str) -> OrderExtraction:
    client = get_anthropic_client()
    response = await client.messages.parse(
        model=MODEL_HAIKU,
        max_tokens=200,
        system=EXTRACT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": message_text}],
        output_format=OrderExtraction,
    )
    return response.parsed_output


async def estimate_delivery(state: GraphState) -> dict:
    intent = state.get("intent")
    if not intent or intent["label"] != "place_order":
        return {}

    business_id = uuid.UUID(state["business_id"])

    async with tenant_session(business_id) as session:
        business = await session.get(Business, business_id)
        rules = business.delivery_rules or {}
        cutoff_hour = rules.get("cutoff_hour", DEFAULT_CUTOFF_HOUR)
        min_lead_hours = rules.get("min_lead_hours", DEFAULT_MIN_LEAD_HOURS)

        # Now runs unconditionally (module docstring) — every place_order needs an address to
        # create the pending-confirmation Order row below, whichever branch it takes.
        extraction = await _extract_order_details(state["message"]["text"])

        # Capability gap (risk_rules.py's NO_CAPABILITY_LABELS) — the agent must never guess
        # an address or the shop's own location, so this escalates rather than answering.
        if not extraction.delivery_address or not business.address:
            return {"delivery_estimate": None}

        # Owner-configured no-delivery locations (Doc 3 roadmap) — checked before the Maps
        # call: deterministic and free, so an excluded address never costs an API call. Routes
        # through the same capability-gap path — no auto-decline reply yet.
        excluded_locations = rules.get("excluded_locations", [])
        if excluded_locations and _matches_excluded_location(
            extraction.delivery_address, excluded_locations
        ):
            return {"delivery_estimate": None}

        customer = await session.get(Customer, uuid.UUID(state["customer_id"]))
        now_amman = datetime.now(AMMAN_TZ)

        if now_amman.time() >= time(cutoff_hour):
            order_reference = f"chat-{uuid.uuid4().hex[:8]}"
            session.add(
                Order(
                    business_id=business_id,
                    order_reference=order_reference,
                    customer_phone=customer.channel_handle if customer else "",
                    status="pending_delivery_estimate",
                    items_summary=f"{extraction.product_count} item(s)",
                    order_date=now_amman,
                    delivery_address=extraction.delivery_address,
                    delivery_window_promised="tomorrow",
                    delivery_status="pending",
                    confirmation_status=OrderConfirmationStatus.pending,
                )
            )
            return {
                "delivery_estimate": {
                    "same_day_eligible": False,
                    "estimated_window": "tomorrow",
                    "reasoning": f"Past the {cutoff_hour}:00 same-day cutoff.",
                    "order_reference": order_reference,
                }
            }

        backlog_count = await session.scalar(
            select(func.count(Order.id)).where(
                Order.business_id == business_id,
                Order.delivery_status == "pending",
                func.date(Order.order_date) == now_amman.date(),
            )
        )

        try:
            transit_minutes = await estimate_transit_minutes(
                business.address, extraction.delivery_address
            )
        except GoogleMapsError:
            return {"delivery_estimate": None}

        estimated_minutes = transit_minutes + backlog_count * MINUTES_PER_ORDER_IN_QUEUE
        low_hours = max(1, estimated_minutes // 60)
        window_text = f"{low_hours}-{low_hours + 1} hours"
        order_reference = f"chat-{uuid.uuid4().hex[:8]}"

        session.add(
            Order(
                business_id=business_id,
                order_reference=order_reference,
                customer_phone=customer.channel_handle if customer else "",
                status="pending_delivery_estimate",
                items_summary=f"{extraction.product_count} item(s)",
                order_date=now_amman,
                delivery_address=extraction.delivery_address,
                delivery_window_promised=window_text,
                delivery_status="pending",
                confirmation_status=OrderConfirmationStatus.pending,
            )
        )

        return {
            "delivery_estimate": {
                "same_day_eligible": True,
                "estimated_window": window_text,
                "reasoning": (
                    f"{backlog_count} order(s) already pending today, ~{transit_minutes} min "
                    f"transit time — better than the usual {min_lead_hours}h minimum since "
                    "it's not a busy day."
                ),
                "order_reference": order_reference,
            }
        }
