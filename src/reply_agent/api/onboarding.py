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

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from reply_agent.auth.dependencies import ensure_business_access, require_business_access
from reply_agent.config import get_settings
from reply_agent.db.models import Business
from reply_agent.db.tenant_session import tenant_session
from reply_agent.onboarding.meta_oauth import EmbeddedSignupError, exchange_code_for_token
from reply_agent.onboarding.page_signup import (
    get_linked_instagram_account_id,
    get_single_page_id,
    subscribe_page_to_app,
)
from reply_agent.onboarding.whatsapp_signup import register_phone_number, subscribe_app_to_waba

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


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

        try:
            token = await exchange_code_for_token(payload.code)
            await subscribe_app_to_waba(payload.waba_id, token)
            await register_phone_number(payload.phone_number_id, token)
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
        },
    )


class PageSignupPayload(BaseModel):
    business_id: uuid.UUID
    code: str


@router.post("/page/callback")
async def page_signup_callback(request: Request, payload: PageSignupPayload) -> dict:
    await ensure_business_access(request, payload.business_id)

    async with tenant_session(payload.business_id) as session:
        business = await session.get(Business, payload.business_id)

        try:
            token = await exchange_code_for_token(payload.code)
            page_id = await get_single_page_id(token)
            instagram_account_id = await get_linked_instagram_account_id(page_id, token)
            await subscribe_page_to_app(page_id, token)
        except EmbeddedSignupError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        channels_connected = {**business.channels_connected, "messenger": {"page_id": page_id}}
        if instagram_account_id:
            channels_connected["instagram"] = {"page_id": page_id}
        business.channels_connected = channels_connected

    return {"connected": True, "instagram_connected": bool(instagram_account_id)}
