from reply_agent.channels.instagram.client import send_text_message as send_instagram_message
from reply_agent.channels.messenger.client import send_text_message as send_messenger_message
from reply_agent.channels.whatsapp.client import send_text_message as send_whatsapp_message
from reply_agent.graph.state import GraphState


async def send_reply(state: GraphState) -> dict:
    customer_handle = state["thread_id"].split(":", 2)[-1]
    text = state["draft_reply"]["text"]

    # A plain if/elif (not a module-level dict of function references) so tests can patch
    # send_whatsapp_message/send_instagram_message/send_messenger_message by name — a dict
    # built at import time would freeze the original references and ignore the patch.
    match state["channel"]:
        case "whatsapp":
            await send_whatsapp_message(to=customer_handle, text=text)
        case "instagram":
            await send_instagram_message(to=customer_handle, text=text)
        case "messenger":
            await send_messenger_message(to=customer_handle, text=text)
        case other:
            raise NotImplementedError(f"send_reply not implemented for channel={other!r}")

    return {"route": "send"}
