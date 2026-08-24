from pydantic import BaseModel

from reply_agent.graph.state import GraphState
from reply_agent.llm.client import MODEL_HAIKU, get_anthropic_client

SELF_CHECK_SYSTEM_PROMPT = """You are a fact-checker for a customer-service AI's drafted reply. \
Your only job is to catch factual and policy errors — not to critique style, tone, or \
completeness.

FAIL the draft only if:
1. It states a specific price, stock level, or delivery promise that is NOT explicitly supported
   by the retrieved context (a fabricated or guessed fact).
2. It promises something the seller's policies explicitly contradict (e.g. a cash refund when
   the policy says exchange-only).
3. It confidently answers about the wrong product/item when the conversation history or
   retrieved context clearly shows a different, better-matching item for what the customer
   actually asked.

You will be given the conversation history — use it. A short follow-up message (e.g. "size L
please") almost always refers back to whatever product was already established earlier in the
conversation, not a fresh, ambiguous question. Don't invent a different product the customer
never mentioned. If the customer used a distinctive descriptive word (e.g. a specific fabric,
style, or color) and only one retrieved item matches that word, treat that as the correct match.

Do NOT fail the draft for any of the following — these are not errors:
- A reasonable interpretation of which product the customer means, without spelling out every
  other unrelated item that also happens to exist.
- Not proactively suggesting a different product/size/variant as an alternative when the one the
  customer actually asked about is unavailable (e.g. not mentioning that a different abaya has
  their size in stock when the one they asked about doesn't). Suggesting alternatives is a sales
  choice for the seller to make, not a factual error — do not fail a draft just for answering
  the exact question asked without upselling or redirecting.
- Not offering to clarify further when the draft already answers the specific question asked.
- Tone, warmth, emoji use, or common colloquial terms of address (e.g. "حبيبتي") — these match
  the seller's normal voice and are not assumptions worth flagging.
- Minor phrasing choices that don't change the actual facts stated.
- An honest "I don't know, let me check" hedge when the context truly doesn't cover the
  question — that is correct behavior, not a failure.
- A specific estimate that falls within a stated range (e.g. saying "might arrive tomorrow,
  inshallah" when the policy says "1-2 business days") — a plausible instance of a range is
  consistent with that range, not a contradiction of it.

If the retrieved context looks insufficient to answer the customer's actual question at all (not
just imprecise), set needs_retry=true so the system can search again — otherwise leave it false.
"""


class SelfCheckOutput(BaseModel):
    passed: bool
    reason: str
    needs_retry: bool


async def self_check(state: GraphState) -> dict:
    draft = state["draft_reply"]
    context_text = "\n\n".join(
        f"[source {c['source']}] {c['snippet']}" for c in state.get("retrieved_context", [])
    )
    history_text = "\n".join(
        f"{t['role']}: {t['text']}" for t in state.get("conversation_history", [])[-6:]
    )
    user_prompt = (
        f"Conversation so far:\n{history_text or '(no prior turns)'}\n\n"
        f"Customer's latest message: {state['message']['text']}\n\n"
        f"Retrieved context:\n{context_text or '(none)'}\n\n"
        f"Drafted reply:\n{draft['text']}"
    )

    client = get_anthropic_client()
    response = await client.messages.parse(
        model=MODEL_HAIKU,
        max_tokens=512,
        system=SELF_CHECK_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
        output_format=SelfCheckOutput,
    )
    result = response.parsed_output

    return {
        "self_check": {
            "passed": result.passed,
            "reason": result.reason,
            "needs_retry": result.needs_retry,
        }
    }
