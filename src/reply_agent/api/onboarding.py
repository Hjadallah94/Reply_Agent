"""Self-serve channel connection (Doc 3 Phase 4): lets a business connect its own WhatsApp
number and/or Facebook Page without us doing it manually. Each channel is its own trigger page
(Meta's JS SDK popup) plus a callback that completes setup once the popup hands back a code —
see onboarding/whatsapp_signup.py and onboarding/page_signup.py for what each callback actually
does and what in these flows is unverified against Meta's real servers so far.

Gated by auth/dependencies.py, same as api/dashboard.py — the GET pages via Depends(), the POST
callbacks via ensure_business_access() since business_id there is a JSON body field, not a path/
query param FastAPI's dependency injection can see.
"""

import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from reply_agent.auth.dependencies import ensure_business_access, require_business_access
from reply_agent.billing.tiers import CHANNEL_LIMIT
from reply_agent.config import get_settings
from reply_agent.db.models import Business
from reply_agent.db.tenant_session import tenant_session
from reply_agent.onboarding.meta_oauth import (
    EmbeddedSignupError,
    exchange_code_for_token,
    get_authorizing_user_id,
)
from reply_agent.onboarding.page_signup import (
    get_linked_instagram_account_id,
    get_single_page_id,
    subscribe_page_to_app,
)
from reply_agent.onboarding.whatsapp_signup import register_phone_number, subscribe_app_to_waba

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _remaining_channel_slots(business: Business) -> int:
    """Doc 3 roadmap (channel choice by tier, 2026-09-09) — how many more channels this business
    can connect, of any kind: a tier grants a *count* of channels, not specific ones, so this is
    purely CHANNEL_LIMIT minus however many are already in Business.channels_connected.
    """
    return CHANNEL_LIMIT[business.plan_tier] - len(business.channels_connected)


@router.get("/whatsapp")
async def whatsapp_signup_page(
    request: Request, business: Business = Depends(require_business_access)
):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "onboarding_whatsapp.html",
        {
            "business": business,
            "meta_app_id": settings.meta_app_id,
            "config_id": settings.meta_embedded_signup_config_id,
            "graph_api_version": settings.meta_graph_api_version,
            "remaining": _remaining_channel_slots(business),
        },
    )


class EmbeddedSignupPayload(BaseModel):
    business_id: uuid.UUID
    code: str
    phone_number_id: str
    waba_id: str


@router.post("/whatsapp/callback")
async def whatsapp_signup_callback(request: Request, payload: EmbeddedSignupPayload) -> dict:
    await ensure_business_access(request, payload.business_id)

    async with tenant_session(payload.business_id) as session:
        business = await session.get(Business, payload.business_id)

        # Doc 3 roadmap (channel choice by tier, 2026-09-09) — WhatsApp now competes for the same
        # per-tier channel-count slots as Instagram/Messenger, rather than being free on every
        # tier. Reconnecting an already-connected WhatsApp number never needs a new slot.
        if (
            "whatsapp" not in business.channels_connected
            and _remaining_channel_slots(business) <= 0
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Your {business.plan_tier.value} plan is limited to "
                    f"{CHANNEL_LIMIT[business.plan_tier]} channel(s), and you've already used "
                    "them all — upgrade to connect more."
                ),
            )

        try:
            token = await exchange_code_for_token(payload.code)
            await subscribe_app_to_waba(payload.waba_id, token)
            await register_phone_number(payload.phone_number_id, token)
            # Doc 3 roadmap — captured so api/meta_compliance.py's deauthorize/data-deletion
            # callbacks can actually find and act on this business later; they only ever
            # receive this same Facebook user id, never a business_id.
            business.facebook_user_id = await get_authorizing_user_id(token)
        except EmbeddedSignupError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        business.channels_connected = {
            **business.channels_connected,
            "whatsapp": {
                "phone_number_id": payload.phone_number_id,
                "waba_id": payload.waba_id,
            },
        }

    return {"connected": True}


@router.get("/page")
async def page_signup_page(request: Request, business: Business = Depends(require_business_access)):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "onboarding_page.html",
        {
            "business": business,
            "meta_app_id": settings.meta_app_id,
            "config_id": settings.meta_page_signup_config_id,
            "graph_api_version": settings.meta_graph_api_version,
            "remaining": _remaining_channel_slots(business),
        },
    )


class PageSignupPayload(BaseModel):
    business_id: uuid.UUID
    code: str
    # Doc 3 roadmap (channel choice by tier, 2026-09-09) — a Page connection can offer Messenger
    # and, if linked, Instagram together; when only one channel slot remains for both, the
    # business picks which one they want (onboarding_page.html's radio choice) rather than the
    # app silently choosing for them. Meaningless (ignored) when 2+ slots remain or the Page only
    # offers one of the two.
    preferred_channel: Literal["messenger", "instagram"] | None = None


@router.post("/page/callback")
async def page_signup_callback(request: Request, payload: PageSignupPayload) -> dict:
    await ensure_business_access(request, payload.business_id)

    async with tenant_session(payload.business_id) as session:
        business = await session.get(Business, payload.business_id)

        already_connected = set(business.channels_connected)
        remaining = CHANNEL_LIMIT[business.plan_tier] - len(already_connected)
        # Doc 3 roadmap (channel choice by tier, 2026-09-09) — checked before spending a Meta API
        # round trip on a plan with no slots left; templates/dashboard.html's toolbar is the
        # primary signal an owner sees, this is the backend's safety net. Reconnecting an
        # already-connected Messenger/Instagram never needs a new slot, so this only blocks a
        # genuinely new connection.
        if remaining <= 0 and not ({"messenger", "instagram"} & already_connected):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Your {business.plan_tier.value} plan is limited to "
                    f"{CHANNEL_LIMIT[business.plan_tier]} channel(s), and you've already used "
                    "them all — upgrade to connect more."
                ),
            )

        try:
            token = await exchange_code_for_token(payload.code)
            page_id = await get_single_page_id(token)
            instagram_account_id = await get_linked_instagram_account_id(page_id, token)
            await subscribe_page_to_app(page_id, token)
            # Same reasoning as whatsapp_signup_callback above — overwrites whatever WhatsApp
            # signup stored if a different Facebook account ran this flow (accepted MVP
            # limitation, see db/models.py's Business.facebook_user_id docstring).
            business.facebook_user_id = await get_authorizing_user_id(token)
        except EmbeddedSignupError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        # Doc 3 roadmap (channel choice by tier, 2026-09-09) — only activate what's newly
        # available (already-connected channels don't need re-activating) and never more than
        # the plan has slots left for (`budget`). Two ways newly_available can outgrow budget:
        # budget is 0 but one channel is genuinely new (e.g. Messenger already used the sole
        # slot, this Page also has Instagram linked — no slot for it at all, so nothing new
        # activates); or budget is 1 and BOTH are newly available (the real ambiguous case) — only
        # here does the business's own stated preference matter, falling back to Messenger by
        # default if they didn't send one, or if they asked for the one this Page doesn't
        # actually have linked.
        newly_available = {"messenger"} - already_connected
        if instagram_account_id:
            newly_available |= {"instagram"} - already_connected

        budget = max(remaining, 0)
        if len(newly_available) <= budget:
            to_activate = newly_available
        elif budget == 0:
            to_activate = set()
        else:
            to_activate = (
                {payload.preferred_channel}
                if payload.preferred_channel in newly_available
                else {"messenger"}
            )

        channels_connected = dict(business.channels_connected)
        if "messenger" in to_activate:
            channels_connected["messenger"] = {"page_id": page_id}
        if "instagram" in to_activate:
            channels_connected["instagram"] = {"page_id": page_id}
        business.channels_connected = channels_connected
        instagram_activated = "instagram" in to_activate

    return {"connected": True, "instagram_connected": instagram_activated}
