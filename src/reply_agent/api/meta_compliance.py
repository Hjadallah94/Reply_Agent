"""Meta platform compliance callbacks required in App Dashboard > Facebook Login for Business >
Settings before App Review: the deauthorize callback and the data deletion request callback.
Both receive the same signed_request POST shape identifying the Facebook user_id who
authorized/is deauthorizing the app (onboarding/meta_signed_request.py) — required by Meta
regardless of whether an app actually stores anything tied to that id.

Doc 3 roadmap: both now act on every Business with a matching facebook_user_id (db/models.py —
captured at signup by api/onboarding.py's two callbacks; never set for manually-onboarded
businesses, which these endpoints correctly leave untouched since there's nothing to match).

Scope, deliberately narrow (confirmed via AskUserQuestion): this only ever severs the Facebook
connection (channels_connected + facebook_user_id itself) — never the business's own account,
subscription, conversations, orders, or catalog. The Facebook login here was only ever used by
the *seller* to connect WhatsApp/Instagram; customers never go through Facebook Login at all,
so a Facebook-identity data-deletion request isn't a request to erase the business's own
independently-collected operational data — wiping all of that from an unauthenticated webhook
would be a far more drastic, harder-to-reverse action than what this callback is actually for.
"""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from reply_agent.config import get_settings
from reply_agent.db.models import Business
from reply_agent.db.session import get_sessionmaker
from reply_agent.onboarding.meta_signed_request import SignedRequestError, parse_signed_request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meta", tags=["meta-compliance"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _verify(signed_request: str) -> dict:
    try:
        return parse_signed_request(signed_request, get_settings().meta_app_secret)
    except SignedRequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _find_businesses_by_facebook_user_id(facebook_user_id: str | None) -> list[Business]:
    # Not tenant-scoped — this is a cross-tenant lookup by Facebook identity, the same
    # reasoning as worker.py's find_business_by_channel_key (we don't know which business this
    # is about until we've looked it up). Not a list comprehension over one expected row: see
    # Business.facebook_user_id's own docstring on why more than one match is possible (though
    # rare) rather than assumed impossible.
    if not facebook_user_id:
        return []
    async with get_sessionmaker()() as session:
        return list(
            (
                await session.scalars(
                    select(Business).where(Business.facebook_user_id == facebook_user_id)
                )
            ).all()
        )


@router.post("/deauthorize")
async def deauthorize(signed_request: str = Form(...)) -> dict:
    payload = _verify(signed_request)
    facebook_user_id = payload.get("user_id")
    businesses = await _find_businesses_by_facebook_user_id(facebook_user_id)

    if not businesses:
        logger.warning(
            "Meta deauthorize received for facebook user_id=%s — no matching business "
            "(manually-onboarded, or this id was never captured).",
            facebook_user_id,
        )
        return {"status": "received"}

    async with get_sessionmaker()() as session:
        for business in businesses:
            db_business = await session.get(Business, business.id)
            db_business.channels_connected = {}
        await session.commit()

    logger.info(
        "Meta deauthorize: cleared channels_connected for %d business(es) matching "
        "facebook_user_id=%s.",
        len(businesses),
        facebook_user_id,
    )
    return {"status": "received"}


@router.post("/data-deletion")
async def data_deletion(request: Request, signed_request: str = Form(...)) -> dict:
    payload = _verify(signed_request)
    facebook_user_id = payload.get("user_id")
    confirmation_code = uuid.uuid4().hex
    businesses = await _find_businesses_by_facebook_user_id(facebook_user_id)

    if not businesses:
        logger.warning(
            "Meta data-deletion request received for facebook user_id=%s, "
            "confirmation_code=%s — no matching business (manually-onboarded, or this id was "
            "never captured).",
            facebook_user_id,
            confirmation_code,
        )
    else:
        async with get_sessionmaker()() as session:
            for business in businesses:
                db_business = await session.get(Business, business.id)
                db_business.channels_connected = {}
                # Severs the link entirely (deauthorize only clears the connection state,
                # leaving facebook_user_id in place for a possible re-connect) — this request
                # is specifically about deleting data tied to that Facebook identity.
                db_business.facebook_user_id = None
            await session.commit()
        logger.info(
            "Meta data-deletion: severed the Facebook connection for %d business(es) matching "
            "facebook_user_id=%s, confirmation_code=%s.",
            len(businesses),
            facebook_user_id,
            confirmation_code,
        )

    status_url = str(request.url_for("data_deletion_status", confirmation_code=confirmation_code))
    return {"url": status_url, "confirmation_code": confirmation_code}


@router.get("/data-deletion/status/{confirmation_code}", name="data_deletion_status")
async def data_deletion_status(request: Request, confirmation_code: str):
    return templates.TemplateResponse(
        request, "data_deletion_status.html", {"confirmation_code": confirmation_code}
    )
