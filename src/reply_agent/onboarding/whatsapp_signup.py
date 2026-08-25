"""Server-side steps of WhatsApp Embedded Signup (Doc 3 Phase 4), run after the JS SDK popup
hands back a code (exchanged via meta_oauth.py) plus the customer's own phone_number_id/waba_id
(Meta's WA_EMBEDDED_SIGNUP postMessage event) — see templates/onboarding_whatsapp.html.

- The exchanged token is only used for these one-time setup calls. Ongoing sends
  (channels/whatsapp/client.py) use our own persistent Tech Provider System User token instead —
  Meta shares access to the customer's WABA with that system user once signup completes, rather
  than issuing a separate long-lived token per customer.
- None of this has been exercised against Meta's real servers yet — it can't be, until
  META_EMBEDDED_SIGNUP_CONFIG_ID exists (a one-time manual step in the Meta App Dashboard, see
  README) and App Review has cleared. Built to the documented contract, same as the WhatsApp
  send client was before its own first live test.
"""

import logging
import secrets

import httpx

from reply_agent.config import get_settings
from reply_agent.onboarding.meta_oauth import EmbeddedSignupError

logger = logging.getLogger(__name__)

__all__ = ["EmbeddedSignupError", "register_phone_number", "subscribe_app_to_waba"]


async def subscribe_app_to_waba(waba_id: str, token: str) -> None:
    """Without this, Meta never delivers webhook events for this customer's WABA to our app —
    the dashboard's "test" button in Meta's own UI can look like it works while skipping this.
    """
    settings = get_settings()
    url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/{waba_id}/subscribed_apps"

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, headers={"Authorization": f"Bearer {token}"})

    if response.status_code >= 400:
        raise EmbeddedSignupError(
            f"WABA webhook subscription failed ({response.status_code}): {response.text}"
        )
    logger.info("Embedded signup: subscribed app to WABA %s webhooks", waba_id)


async def register_phone_number(phone_number_id: str, token: str) -> None:
    """Required once before a newly-connected number can send/receive via Cloud API. Generates
    a fresh 6-digit two-step-verification PIN and discards it — re-registering later (token
    issues, migrating) is a rare manual troubleshooting step this flow doesn't handle.
    """
    settings = get_settings()
    pin = f"{secrets.randbelow(1_000_000):06d}"
    url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/{phone_number_id}/register"
    payload = {"messaging_product": "whatsapp", "pin": pin}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            url, json=payload, headers={"Authorization": f"Bearer {token}"}
        )

    if response.status_code >= 400:
        raise EmbeddedSignupError(
            f"Phone number registration failed ({response.status_code}): {response.text}"
        )
    logger.info("Embedded signup: registered phone number %s for Cloud API", phone_number_id)
