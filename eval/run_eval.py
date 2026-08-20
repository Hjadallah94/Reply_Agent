"""Replays eval/conversations/*.yaml through the real graph (real Anthropic + Voyage calls) and
reports whether the final route matched what was expected (Doc 3, Phase 1: "run the evaluation
set... do not proceed until auto-resolution and escalation-precision targets are within reach").

This is NOT a CI-safe unit test — it costs real API calls and needs a seeded business
(run scripts/seed_business.py first) plus ANTHROPIC_API_KEY / VOYAGE_API_KEY set, with
WHATSAPP_DRY_RUN=true so send/escalate notifications don't try to hit the real Graph API.

Usage: uv run python eval/run_eval.py
"""

import asyncio
import sys
from pathlib import Path

import yaml
from sqlalchemy import delete, select

from reply_agent.db.models import Business, ChannelType, Message, MessageDirection
from reply_agent.db.session import get_sessionmaker
from reply_agent.graph.context_resolution import get_or_create_conversation, get_or_create_customer
from reply_agent.graph.graph import run_graph

CONVERSATIONS_DIR = Path(__file__).parent / "conversations"
BUSINESS_NAME = "Rose Abaya House"


async def run_one(conversation_id: str, convo: dict) -> dict:
    session_maker = get_sessionmaker()

    async with session_maker() as session:
        business = await session.scalar(select(Business).where(Business.name == BUSINESS_NAME))
        if business is None:
            raise RuntimeError(
                f"Business {BUSINESS_NAME!r} not found — run scripts/seed_business.py first"
            )

        customer = await get_or_create_customer(
            session, business.id, ChannelType.whatsapp, f"eval-{conversation_id}"
        )
        conversation = await get_or_create_conversation(
            session, business.id, ChannelType.whatsapp, customer
        )
        # Clean slate on re-run so conversation_history reflects only this fixture's turns.
        await session.execute(delete(Message).where(Message.conversation_id == conversation.id))

        turns = convo["turns"]
        prior_turns, last_turn = turns[:-1], turns[-1]
        for i, turn in enumerate(prior_turns):
            direction = (
                MessageDirection.inbound
                if turn["role"] == "customer"
                else MessageDirection.outbound
            )
            session.add(
                Message(
                    conversation_id=conversation.id,
                    direction=direction,
                    text=turn["text"],
                    channel_message_id=f"eval-{conversation_id}-{i}",
                )
            )
        await session.commit()

        business_id = str(business.id)
        thread_id = conversation.thread_id
        customer_id = str(customer.id)

    initial_state = {
        "business_id": business_id,
        "channel": "whatsapp",
        "customer_id": customer_id,
        "thread_id": thread_id,
        "message": {
            "text": last_turn["text"],
            "media_refs": [],
            "received_at": "2026-08-20T12:00:00Z",
            "channel_message_id": f"eval-{conversation_id}-final",
        },
        "conversation_history": [],
        "customer_profile": {"past_orders": [], "preferences": {}, "prior_escalations": 0},
    }

    return await run_graph(initial_state, thread_id=thread_id)


async def main() -> None:
    files = sorted(CONVERSATIONS_DIR.glob("*.yaml"))
    if not files:
        print(f"No conversation fixtures found in {CONVERSATIONS_DIR}")
        sys.exit(1)

    passed, failed = 0, 0
    for path in files:
        conversation_id = path.stem
        convo = yaml.safe_load(path.read_text(encoding="utf-8"))
        expected_route = convo["expected"]["route"]

        try:
            result = await run_one(conversation_id, convo)
        except Exception as exc:  # noqa: BLE001 - eval harness reports, doesn't crash the run
            print(f"ERROR  {conversation_id}: {exc}")
            failed += 1
            continue

        actual_route = result.get("route")
        model_used = result.get("draft_reply", {}).get("model_used", "-")
        ok = actual_route == expected_route
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
        status = "PASS" if ok else "FAIL"
        print(
            f"{status}  {conversation_id}: expected={expected_route} "
            f"actual={actual_route} model={model_used}"
        )

    print(f"\n{passed}/{passed + failed} passed")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
