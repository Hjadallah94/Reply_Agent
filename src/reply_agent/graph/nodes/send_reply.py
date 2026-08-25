import uuid

from reply_agent.channels.instagram.client import send_text_message as send_instagram_message
from reply_agent.channels.messenger.client import send_text_message as send_messenger_message
from reply_agent.channels.whatsapp.client import send_text_message as send_whatsapp_message
from reply_agent.db.models import ChannelType
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.context_resolution import get_page_id, get_whatsapp_phone_number_id
from reply_agent.graph.state import GraphState


async def send_reply(state: GraphState) -> dict:
    customer_handle = state["thread_id"].split(":", 2)[-1]
    text = state["draft_reply"]["text"]
    business_id = uuid.UUID(state["business_id"])

    # A plain if/elif (not a module-level dict of function references) so tests can patch
    # send_whatsapp_message/send_instagram_message/send_messenger_message by name — a dict
    # built at import time would freeze the original references and ignore the patch.
    match state["channel"]:
        case "whatsapp":
            async with tenant_session(business_id) as session:
                phone_number_id = await get_whatsapp_phone_number_id(session, business_id)
            await send_whatsapp_message(
                to=customer_handle, text=text, phone_number_id=phone_number_id
            )
        case "instagram":
            async with tenant_session(business_id) as session:
                page_id = await get_page_id(session, business_id, ChannelType.instagram)
            await send_instagram_message(to=customer_handle, text=text, page_id=page_id)
        case "messenger":
            async with tenant_session(business_id) as session:
                page_id = await get_page_id(session, business_id, ChannelType.messenger)
            await send_messenger_message(to=customer_handle, text=text, page_id=page_id)
        case other:
            raise NotImplementedError(f"send_reply not implemented for channel={other!r}")

    return {"route": "send"}
