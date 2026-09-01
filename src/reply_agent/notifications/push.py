"""Web Push notifications (Doc 3 Phase 6.6) — supplements, never replaces, the existing
WhatsApp owner-ping (graph/nodes/escalate_to_owner.py and graph/nodes/request_owner_approval.py
already send that, independently of this). Entirely inert if VAPID keys aren't configured
(settings.vapid_public_key/vapid_private_key empty) — same graceful-when-unconfigured
convention as the WhatsApp ping itself (config.owner_notification_whatsapp_number).
"""

import asyncio
import json
import logging
import uuid

from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from reply_agent.config import get_settings
from reply_agent.db.models import PushSubscription

logger = logging.getLogger(__name__)

# The standard Web Push signal that a subscription is dead (browser uninstalled, permission
# revoked, etc.) — normal lifecycle, not an error worth surfacing, just something to clean up.
_EXPIRED_STATUS_CODES = {404, 410}


def _send_one(subscription: PushSubscription, payload: str) -> None:
    """Synchronous (pywebpush uses requests, not httpx) — always called via asyncio.to_thread
    so it never blocks the event loop. Split out from send_push_to_business so tests can mock
    just this one call rather than the whole pywebpush/requests stack.
    """
    settings = get_settings()
    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh_key, "auth": subscription.auth_key},
        },
        data=payload,
        vapid_private_key=settings.vapid_private_key,
        vapid_claims={"sub": settings.vapid_subject},
    )


async def send_push_to_business(
    session: AsyncSession, business_id: uuid.UUID, *, title: str, body: str, url: str
) -> None:
    settings = get_settings()
    if not settings.vapid_public_key or not settings.vapid_private_key:
        return

    subscriptions = (
        await session.scalars(
            select(PushSubscription).where(PushSubscription.business_id == business_id)
        )
    ).all()
    if not subscriptions:
        return

    payload = json.dumps({"title": title, "body": body, "url": url})
    for subscription in subscriptions:
        try:
            await asyncio.to_thread(_send_one, subscription, payload)
        except WebPushException as exc:
            if exc.status_code in _EXPIRED_STATUS_CODES:
                await session.execute(
                    delete(PushSubscription).where(PushSubscription.id == subscription.id)
                )
            else:
                logger.warning("Push send failed for subscription %s: %s", subscription.id, exc)
