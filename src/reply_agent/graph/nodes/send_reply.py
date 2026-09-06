import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reply_agent.channels.instagram.client import (
    send_image_message as send_instagram_image,
)
from reply_agent.channels.instagram.client import send_text_message as send_instagram_message
from reply_agent.channels.messenger.client import (
    send_image_message as send_messenger_image,
)
from reply_agent.channels.messenger.client import send_text_message as send_messenger_message
from reply_agent.channels.whatsapp.client import send_image_message as send_whatsapp_image
from reply_agent.channels.whatsapp.client import send_text_message as send_whatsapp_message
from reply_agent.config import get_settings
from reply_agent.db.models import ChannelType, KnowledgeDocType, KnowledgeDocument, ProductImage
from reply_agent.db.tenant_session import tenant_session
from reply_agent.graph.context_resolution import get_page_id, get_whatsapp_phone_number_id
from reply_agent.graph.state import GraphState


async def _find_cited_product_image(
    session: AsyncSession, cited_sources: list[str]
) -> KnowledgeDocument | None:
    """Doc 3 roadmap ("agent can send photo samples") — the first cited source (already
    ordered by retrieve_knowledge.py's vector-similarity score) that's a product with a photo
    on file. Deterministic, not LLM-decided: the draft's own citations already establish which
    product is actually relevant to this reply, same "code decides mechanics, the LLM only
    drafts text" philosophy as delivery estimates and order confirmations elsewhere in this
    codebase. Non-UUID sources (e.g. "order:<id>") are skipped, not errors — order-status
    replies never cite a product.
    """
    for source in cited_sources:
        try:
            document_id = uuid.UUID(source)
        except ValueError:
            continue
        document = await session.get(KnowledgeDocument, document_id)
        if document is None or document.type != KnowledgeDocType.product:
            continue
        has_image = await session.scalar(
            select(ProductImage.id).where(ProductImage.document_id == document_id)
        )
        if has_image is not None:
            return document
    return None


def _product_image_caption(document: KnowledgeDocument) -> str:
    name = document.structured_data.get("name", "")
    price = document.structured_data.get("price_jod")
    return f"{name} — {price} JOD" if price is not None else name


async def _maybe_send_product_image(
    state: GraphState, business_id: uuid.UUID, customer_handle: str
) -> None:
    settings = get_settings()
    if not settings.app_base_url:
        # Can't build a URL Meta's servers could actually fetch — same gating
        # escalate_to_owner.py's push_url already uses for the same reason.
        return

    cited_sources = state.get("draft_reply", {}).get("cited_sources", [])
    if not cited_sources:
        return

    async with tenant_session(business_id) as session:
        document = await _find_cited_product_image(session, cited_sources)
    if document is None:
        return

    image_url = f"{settings.app_base_url}/public/products/{document.id}/image"
    caption = _product_image_caption(document)

    # Same reasoning as send_reply's own match statement below: a plain match, not a dict of
    # function references, so tests can patch send_whatsapp_image/send_instagram_image/
    # send_messenger_image by name.
    match state["channel"]:
        case "whatsapp":
            async with tenant_session(business_id) as session:
                phone_number_id = await get_whatsapp_phone_number_id(session, business_id)
            await send_whatsapp_image(
                to=customer_handle,
                image_url=image_url,
                phone_number_id=phone_number_id,
                caption=caption,
            )
        case "instagram":
            async with tenant_session(business_id) as session:
                page_id = await get_page_id(session, business_id, ChannelType.instagram)
            await send_instagram_image(to=customer_handle, image_url=image_url, page_id=page_id)
        case "messenger":
            async with tenant_session(business_id) as session:
                page_id = await get_page_id(session, business_id, ChannelType.messenger)
            await send_messenger_image(to=customer_handle, image_url=image_url, page_id=page_id)


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

    # Doc 3 roadmap ("agent can send photo samples") — only ever reachable here with real
    # cited_sources when generate_response.py actually drafted this reply (the genuine
    # auto-send path); send_away_reply.py/send_order_catalog_reply.py call this same function
    # with a synthetic draft_reply that carries no cited_sources at all, so this is a no-op
    # for both of those without any extra route-checking.
    await _maybe_send_product_image(state, business_id, customer_handle)

    return {"route": "send"}
