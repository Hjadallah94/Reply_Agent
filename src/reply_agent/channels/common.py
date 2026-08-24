"""Shared internal message shape every channel's webhook normalizes into (Doc 2 Section 2.1:
"converge on one internal schema immediately so nothing downstream needs to know which app
the message came from"). worker.py and context_resolution.py operate only on this shape —
this is what makes "one brain, three channels" (Doc 1) actually true in the code, not just
the pitch.

Also holds the Messenger-Platform-style webhook parsing and Send API logic shared by Instagram
Messaging and Messenger Platform — Meta's "messaging" array format has been the same across
both products for years, but re-verify against Meta's current docs before go-live, same as
the WhatsApp client (channels/whatsapp/client.py).
"""

import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel

from reply_agent.config import get_settings
from reply_agent.db.models import ChannelType
from reply_agent.queue.redis_client import get_redis_async
from reply_agent.queue.tasks import enqueue_inbound_message

logger = logging.getLogger(__name__)

DEDUP_TTL_SECONDS = 60 * 60 * 24


class NormalizedInboundEvent(BaseModel):
    channel: ChannelType
    business_lookup_key: str  # WA: phone_number_id. IG/Messenger: the connected Page ID.
    customer_handle: str  # WA: phone number. IG: IGSID. Messenger: PSID.
    text: str
    channel_message_id: str
    received_at: str


def verify_meta_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Same X-Hub-Signature-256 scheme across all three Meta webhook products."""
    settings = get_settings()
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.meta_app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


def extract_messaging_events(payload: dict, channel: ChannelType) -> list[NormalizedInboundEvent]:
    """Parses the "messaging" array webhook shape shared by Instagram Messaging and Messenger
    Platform. Only plain text messages are handled for now (Doc 3 Phase 2 scope) — echoes of
    our own outbound sends and non-text messages (image, sticker, ...) are skipped.
    """
    events: list[NormalizedInboundEvent] = []
    for entry in payload.get("entry", []):
        page_id = str(entry.get("id", ""))
        for item in entry.get("messaging", []):
            message = item.get("message")
            if not message or message.get("is_echo") or "text" not in message:
                continue
            events.append(
                NormalizedInboundEvent(
                    channel=channel,
                    business_lookup_key=page_id,
                    customer_handle=str(item["sender"]["id"]),
                    text=message["text"],
                    channel_message_id=message["mid"],
                    received_at=str(item.get("timestamp", "")),
                )
            )
    return events


def build_messaging_webhook_router(
    *, channel: ChannelType, prefix: str, expected_object: str
) -> APIRouter:
    """GET verification + POST receive for Instagram Messaging / Messenger Platform — identical
    shape for both (Meta's shared "messaging" webhook format), parametrized by channel/prefix/
    the "object" field each product sends ("instagram" vs "page").
    """
    router = APIRouter(prefix=prefix, tags=[channel.value])

    @router.get("")
    async def verify_webhook(
        hub_mode: str = Query(alias="hub.mode"),
        hub_verify_token: str = Query(alias="hub.verify_token"),
        hub_challenge: str = Query(alias="hub.challenge"),
    ) -> Response:
        settings = get_settings()
        if hub_mode != "subscribe" or hub_verify_token != settings.meta_webhook_verify_token:
            raise HTTPException(status_code=403, detail="Verification token mismatch")
        return Response(content=hub_challenge, media_type="text/plain")

    @router.post("")
    async def receive_webhook(
        request: Request, x_hub_signature_256: str | None = Header(default=None)
    ) -> Response:
        raw_body = await request.body()
        if not verify_meta_signature(raw_body, x_hub_signature_256):
            raise HTTPException(status_code=403, detail="Invalid signature")

        payload = await request.json()
        if payload.get("object") != expected_object:
            # Not this product's event (Meta can fan the same app-level webhook URL out to
            # multiple object types) — ack anyway so Meta doesn't retry it as a failure.
            return Response(status_code=200)

        redis_client = get_redis_async()
        for event in extract_messaging_events(payload, channel):
            dedup_key = f"{channel.value}:dedup:{event.channel_message_id}"
            is_new = await redis_client.set(dedup_key, "1", nx=True, ex=DEDUP_TTL_SECONDS)
            if not is_new:
                logger.info("Skipping duplicate webhook delivery for %s", event.channel_message_id)
                continue
            enqueue_inbound_message(event.model_dump())

        return Response(status_code=200)

    return router


class MetaSendError(RuntimeError):
    pass


async def send_page_message(to: str, text: str) -> dict:
    """Messenger Send API — also used for Instagram Messaging (same endpoint shape, same Page
    access token, since IG messaging is accessed via the connected Facebook Page).
    """
    settings = get_settings()

    if settings.meta_dry_run:
        logger.info("[dry-run] Meta page send to %s: %s", to, text)
        return {"dry_run": True, "to": to, "text": text}

    url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/me/messages"
    payload = {
        "recipient": {"id": to},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }
    headers = {"Authorization": f"Bearer {settings.meta_page_access_token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code >= 400:
        raise MetaSendError(f"Meta page send failed ({response.status_code}): {response.text}")

    return response.json()
