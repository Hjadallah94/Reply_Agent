"""Minimal WhatsApp Cloud API send client. The text-message send shape here has been stable
for a long time, but re-verify META_GRAPH_API_VERSION and this endpoint against Meta's current
developer docs before go-live — Meta revs the Graph API version roughly yearly and can add
requirements (e.g. template categories, messaging-window enforcement details).
"""

import logging

import httpx

from reply_agent.config import get_settings

logger = logging.getLogger(__name__)


class WhatsAppSendError(RuntimeError):
    pass


async def send_text_message(to: str, text: str) -> dict:
    settings = get_settings()

    if settings.whatsapp_dry_run:
        logger.info("[dry-run] WhatsApp send to %s: %s", to, text)
        return {"dry_run": True, "to": to, "text": text}

    url = (
        f"https://graph.facebook.com/{settings.meta_graph_api_version}"
        f"/{settings.whatsapp_phone_number_id}/messages"
    )
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    headers = {"Authorization": f"Bearer {settings.whatsapp_access_token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code >= 400:
        raise WhatsAppSendError(f"WhatsApp send failed ({response.status_code}): {response.text}")

    return response.json()
