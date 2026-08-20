from pydantic import BaseModel

from reply_agent.graph.state import GraphState
from reply_agent.llm.client import MODEL_HAIKU, get_anthropic_client

SELF_CHECK_SYSTEM_PROMPT = """You are a strict fact-checker for a customer-service AI's drafted \
reply.
Verify:
1. Every price, stock level, or delivery promise in the draft is explicitly supported by the
   retrieved context. If the draft states any such fact that isn't in the context, this fails.
2. The draft doesn't promise anything the seller's policies don't support.
3. The tone is appropriate for a small Jordanian online seller talking to a customer.

If the retrieved context looks insufficient to answer the customer's question at all (not just
imprecise), set needs_retry=true so the system can search again — otherwise leave it false.
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
    user_prompt = (
        f"Customer's message: {state['message']['text']}\n\n"
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
