"""The one piece shared by every Facebook Login for Business flow (Doc 3 Phase 4) — WhatsApp
Embedded Signup and the Page-based login used for Instagram/Messenger both hand back a
short-lived code (response_type=code, override_default_response_type=true) that gets exchanged
here the same way, regardless of which flow produced it. No redirect_uri: that's the standard
web-redirect OAuth shape, not this one (the JS SDK popup variant). The code expires in ~30
seconds. Not exercised against Meta's real servers yet — see onboarding/whatsapp_signup.py and
onboarding/page_signup.py for what depends on it and what's still unverified.
"""

import logging

import httpx

from reply_agent.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddedSignupError(RuntimeError):
    pass


async def exchange_code_for_token(code: str) -> str:
    settings = get_settings()
    url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/oauth/access_token"
    params = {
        "client_id": settings.meta_app_id,
        "client_secret": settings.meta_app_secret,
        "code": code,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, params=params)

    if response.status_code >= 400:
        raise EmbeddedSignupError(f"Code exchange failed ({response.status_code}): {response.text}")
    logger.info("Embedded signup: exchanged code for a business token")
    return response.json()["access_token"]


async def get_authorizing_user_id(token: str) -> str:
    """The Facebook user id who granted this login — api/onboarding.py stores it on the
    Business row so api/meta_compliance.py's deauthorize/data-deletion callbacks (which only
    ever receive this same user_id, never a business_id) can actually find and act on the
    right business, instead of only logging the event for manual follow-up.
    """
    settings = get_settings()
    url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/me"

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {token}"})

    if response.status_code >= 400:
        raise EmbeddedSignupError(
            f"Fetching the authorizing user's id failed ({response.status_code}): {response.text}"
        )
    return response.json()["id"]
