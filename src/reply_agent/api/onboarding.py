"""WhatsApp Embedded Signup (Doc 3 Phase 4): lets a business connect its own WhatsApp number
without us doing it manually. Two halves: /onboarding/whatsapp (the trigger page, Meta's JS SDK
popup — templates/onboarding_whatsapp.html) and the callback below that completes setup once
the popup hands back a code. See onboarding/whatsapp_signup.py for what the callback actually
does and what in this flow is unverified against Meta's real servers so far.

No auth — same internal-MVP caveat as the rest of the dashboard (api/dashboard.py).
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from reply_agent.config import get_settings
from reply_agent.db.models import Business
from reply_agent.db.session import get_sessionmaker
from reply_agent.onboarding.whatsapp_signup import (
    EmbeddedSignupError,
    exchange_code_for_token,
    register_phone_number,
    subscribe_app_to_waba,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/whatsapp")
async def whatsapp_signup_page(request: Request, business_id: uuid.UUID):
    async with get_sessionmaker()() as session:
        business = await session.get(Business, business_id)
        if business is None:
            raise HTTPException(status_code=404, detail="Business not found")

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
async def whatsapp_signup_callback(payload: EmbeddedSignupPayload) -> dict:
    async with get_sessionmaker()() as session:
        business = await session.get(Business, payload.business_id)
        if business is None:
            raise HTTPException(status_code=404, detail="Business not found")

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
        await session.commit()

    return {"connected": True}
