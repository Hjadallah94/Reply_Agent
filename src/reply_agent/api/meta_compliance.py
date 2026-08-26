"""Meta platform compliance callbacks required in App Dashboard > Facebook Login for Business >
Settings before App Review: the deauthorize callback and the data deletion request callback.
Both receive the same signed_request POST shape identifying the Facebook user_id who
authorized/is deauthorizing the app (onboarding/meta_signed_request.py) — required by Meta
regardless of whether an app actually stores anything tied to that id.

Neither callback can act on a specific Business here: onboarding/page_signup.py and
whatsapp_signup.py never captured the connecting Facebook user's id, only the Page/WABA/
phone_number_id they connected (db/models.py's Business.channels_connected). So both endpoints
satisfy Meta's required contract — verify the signature, respond in the exact shape App Review
checks for — and log the event for manual follow-up rather than claiming an automatic data wipe
that isn't actually targeted at anything. Capturing that user_id at signup so this can become
fully automatic is a follow-up, not done here.
"""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates

from reply_agent.config import get_settings
from reply_agent.onboarding.meta_signed_request import SignedRequestError, parse_signed_request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meta", tags=["meta-compliance"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _verify(signed_request: str) -> dict:
    try:
        return parse_signed_request(signed_request, get_settings().meta_app_secret)
    except SignedRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/deauthorize")
async def deauthorize(signed_request: str = Form(...)) -> dict:
    payload = _verify(signed_request)
    logger.warning(
        "Meta deauthorize received for facebook user_id=%s — no business mapping stored for "
        "that id, channels_connected NOT cleared automatically; needs manual follow-up.",
        payload.get("user_id"),
    )
    return {"status": "received"}


@router.post("/data-deletion")
async def data_deletion(request: Request, signed_request: str = Form(...)) -> dict:
    payload = _verify(signed_request)
    confirmation_code = uuid.uuid4().hex
    logger.warning(
        "Meta data-deletion request received for facebook user_id=%s, "
        "confirmation_code=%s — no business mapping stored for that id, nothing deleted "
        "automatically; needs manual follow-up.",
        payload.get("user_id"),
        confirmation_code,
    )
    status_url = str(request.url_for("data_deletion_status", confirmation_code=confirmation_code))
    return {"url": status_url, "confirmation_code": confirmation_code}


@router.get("/data-deletion/status/{confirmation_code}", name="data_deletion_status")
async def data_deletion_status(request: Request, confirmation_code: str):
    return templates.TemplateResponse(
        request, "data_deletion_status.html", {"confirmation_code": confirmation_code}
    )
