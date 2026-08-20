"""WhatsApp Cloud API webhook receiver (Doc 2 Section 2.1). Verifies Meta's signature,
normalizes each text message, deduplicates via Redis (Meta retries undelivered webhooks),
and enqueues onto the RQ queue — the actual LangGraph pipeline runs in the worker, not here,
so this handler stays fast regardless of LLM latency.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response

from reply_agent.channels.whatsapp.schemas import extract_text_messages
from reply_agent.config import get_settings
from reply_agent.queue.redis_client import get_redis_async
from reply_agent.queue.tasks import enqueue_inbound_message

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])

DEDUP_TTL_SECONDS = 60 * 60 * 24


@router.get("")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    settings = get_settings()
    if hub_mode != "subscribe" or hub_verify_token != settings.whatsapp_webhook_verify_token:
        raise HTTPException(status_code=403, detail="Verification token mismatch")
    return Response(content=hub_challenge, media_type="text/plain")


def _verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    settings = get_settings()
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.meta_app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header.removeprefix("sha256="))


@router.post("")
async def receive_webhook(
    request: Request, x_hub_signature_256: str | None = Header(default=None)
) -> Response:
    raw_body = await request.body()
    if not _verify_signature(raw_body, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    redis_client = get_redis_async()

    for message in extract_text_messages(payload):
        dedup_key = f"wa:dedup:{message.channel_message_id}"
        is_new = await redis_client.set(dedup_key, "1", nx=True, ex=DEDUP_TTL_SECONDS)
        if not is_new:
            logger.info("Skipping duplicate webhook delivery for %s", message.channel_message_id)
            continue
        enqueue_inbound_message(message.model_dump())

    # Meta expects a fast 200 regardless of downstream processing outcome.
    return Response(status_code=200)
