"""Server-side steps of connecting a business's Facebook Page for Messenger + Instagram
messaging (Doc 3 Phase 4) — Meta's standard Facebook Login for Business flow, not WhatsApp's
Embedded Signup (see whatsapp_signup.py for that one; both share meta_oauth.py's code exchange).

One Page connection covers both channels: Instagram Messaging is accessed through whichever
Facebook Page the customer's Instagram professional account is linked to, so this checks for
that link (instagram_business_account) and sets channels_connected for both "messenger" and
"instagram" when present, rather than running two near-identical flows for one real-world action.

MVP scope: a business with more than one Facebook Page granted during login is rejected with a
clear error rather than offering a picker — Doc 1's target seller is a solo/small operation with
one Page, and building a full asset-picker UI isn't worth it until real usage says otherwise.

Not exercised against Meta's real servers yet — see onboarding/whatsapp_signup.py for the same
caveat and what unblocks it (this flow's own config_id, META_PAGE_SIGNUP_CONFIG_ID, plus App
Review clearing for pages_messaging / instagram_manage_messages).
"""

import logging

import httpx

from reply_agent.config import get_settings
from reply_agent.onboarding.meta_oauth import EmbeddedSignupError

logger = logging.getLogger(__name__)


class NoPageSelectedError(EmbeddedSignupError):
    pass


class MultiplePagesError(EmbeddedSignupError):
    pass


async def list_granted_pages(token: str) -> list[dict]:
    settings = get_settings()
    url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/me/accounts"

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {token}"})

    if response.status_code >= 400:
        raise EmbeddedSignupError(f"Listing Pages failed ({response.status_code}): {response.text}")
    return response.json().get("data", [])


async def get_single_page_id(token: str) -> str:
    pages = await list_granted_pages(token)
    if not pages:
        raise NoPageSelectedError("No Facebook Page was granted during login.")
    if len(pages) > 1:
        raise MultiplePagesError(
            f"{len(pages)} Pages were granted — connecting more than one Page per business "
            "isn't supported yet. Grant access to a single Page and try again."
        )
    return pages[0]["id"]


async def get_linked_instagram_account_id(page_id: str, token: str) -> str | None:
    settings = get_settings()
    url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/{page_id}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            url,
            params={"fields": "instagram_business_account"},
            headers={"Authorization": f"Bearer {token}"},
        )

    if response.status_code >= 400:
        raise EmbeddedSignupError(
            f"Checking for a linked Instagram account failed "
            f"({response.status_code}): {response.text}"
        )
    account = response.json().get("instagram_business_account")
    return account["id"] if account else None


async def subscribe_page_to_app(page_id: str, token: str) -> None:
    settings = get_settings()
    url = f"https://graph.facebook.com/{settings.meta_graph_api_version}/{page_id}/subscribed_apps"
    params = {"subscribed_fields": "messages,messaging_postbacks"}
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, params=params, headers=headers)

    if response.status_code >= 400:
        raise EmbeddedSignupError(
            f"Page webhook subscription failed ({response.status_code}): {response.text}"
        )
    logger.info("Embedded signup: subscribed app to Page %s webhooks", page_id)
