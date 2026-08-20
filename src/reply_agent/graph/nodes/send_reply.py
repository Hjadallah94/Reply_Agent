from reply_agent.channels.whatsapp.client import send_text_message
from reply_agent.graph.state import GraphState


async def send_reply(state: GraphState) -> dict:
    if state["channel"] != "whatsapp":
        # Instagram/Messenger land in Phase 2 (Doc 3) — reusing this same graph.
        raise NotImplementedError(
            f"send_reply not yet implemented for channel={state['channel']!r}"
        )

    customer_handle = state["thread_id"].split(":", 2)[-1]
    await send_text_message(to=customer_handle, text=state["draft_reply"]["text"])

    return {"route": "send"}
