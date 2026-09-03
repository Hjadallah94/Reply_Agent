import uuid

from sqlalchemy import select

from reply_agent.db.models import (
    Business,
    CustomRule,
    CustomRuleStatus,
    KnowledgeDocType,
    KnowledgeDocument,
)
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.state import GraphState
from reply_agent.llm.client import get_anthropic_client
from reply_agent.llm.prompts.system import build_system_prompt
from reply_agent.llm.routing import pick_generation_model

BRAND_VOICE_LIMIT = 5


async def generate_response(state: GraphState) -> dict:
    business_id = uuid.UUID(state["business_id"])

    async with tenant_session(business_id) as session:
        business = await session.get(Business, business_id)
        brand_voice_docs = (
            await session.scalars(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.business_id == business_id,
                    KnowledgeDocument.type == KnowledgeDocType.brand_voice,
                )
                # Most-recent-first: without this, an unordered LIMIT returns an arbitrary 5
                # once a business has more than that many — a real owner correction (Doc 1
                # Section 7) could sit in the table forever and never actually reach a prompt.
                .order_by(KnowledgeDocument.updated_at.desc())
                .limit(BRAND_VOICE_LIMIT)
            )
        ).all()

        # Doc 3 roadmap (partner meeting 2026-09-01) — only approved custom rules reach the
        # prompt; a pending or rejected one is inert (see db/models.py's CustomRule docstring).
        approved_rules = (
            await session.scalars(
                select(CustomRule).where(
                    CustomRule.business_id == business_id,
                    CustomRule.status == CustomRuleStatus.approved,
                )
            )
        ).all()

    retrieved_context = state.get("retrieved_context", [])
    context_text = "\n\n".join(f"[source {c['source']}] {c['snippet']}" for c in retrieved_context)

    # Doc 3 roadmap (order confirmation layer) — a place_order draft asks the customer to
    # confirm rather than declaring the order placed, unless they already have (reached via
    # classify_confirmation_reply's "confirmed" branch) or there's nothing yet to confirm
    # (no delivery_estimate means this is a capability gap, escalating regardless of the draft).
    order_intent = state.get("intent") or {}
    require_order_confirmation = (
        order_intent.get("label") == "place_order"
        and state.get("order_confirmation_decision") != "confirmed"
        and state.get("delivery_estimate") is not None
    )

    system_prompt = build_system_prompt(
        business_name=business.name if business else "this seller",
        brand_voice_examples=[doc.content for doc in brand_voice_docs],
        retrieved_context=context_text,
        delivery_estimate=state.get("delivery_estimate"),
        custom_rules=[rule.rule_text for rule in approved_rules],
        require_order_confirmation=require_order_confirmation,
    )

    history = state["conversation_history"][-6:]
    messages = [
        {"role": "user" if t["role"] == "customer" else "assistant", "content": t["text"]}
        for t in history
    ]
    messages.append({"role": "user", "content": state["message"]["text"]})

    intent = state.get("intent", {"confidence": 0.5})
    is_retry = state.get("self_check", {}).get("needs_retry", False)
    model = pick_generation_model(
        intent_confidence=intent.get("confidence", 0.5),
        conversation_turn_count=len(state["conversation_history"]),
        is_retry=is_retry,
    )

    client = get_anthropic_client()
    response = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )
    reply_text = next((b.text for b in response.content if b.type == "text"), "")

    return {
        "draft_reply": {
            "text": reply_text,
            "cited_sources": [c["source"] for c in retrieved_context],
            "model_used": model,
        },
        # Doc 3 roadmap (order confirmation follow-up) — carried into state so
        # update_memory.py knows, once this send actually happens, whether it was a
        # confirmation-request draft (needing the nudge job scheduled) without recomputing
        # this same condition itself.
        "require_order_confirmation": require_order_confirmation,
    }
