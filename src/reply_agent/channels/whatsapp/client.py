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


async def send_text_message(to: str, text: str, phone_number_id: str) -> dict:
    """phone_number_id is the sending business's own number (Business.channels_connected),
    never a global default — otherwise every onboarded business's replies would go out under
    whichever number happened to be in settings. The bearer token, by contrast, genuinely is
    one shared value across every business: it's our Tech Provider System User token, which
    gains access to each customer's WABA as they complete embedded signup (Doc 3 Phase 4) —
    Meta's model shares access to the WABA with our system user, not a separate per-customer
    token for ongoing sends.
    """
    settings = get_settings()

    if settings.meta_dry_run:
        logger.info("[dry-run] WhatsApp send to %s via %s: %s", to, phone_number_id, text)
        return {"dry_run": True, "to": to, "text": text}

    url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/{phone_number_id}/messages"
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
