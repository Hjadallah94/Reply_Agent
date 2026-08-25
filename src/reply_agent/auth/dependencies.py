"""FastAPI dependencies gating the dashboard and onboarding routes. Session-based (Starlette's
signed-cookie SessionMiddleware, app.py) — no server-side session table, the cookie itself holds
{"user_id": ...}. A 303 redirect to /login (not a 401) since every route this guards renders an
HTML page or is called from one — a bare 401 JSON body isn't useful to a browser navigating here.
"""

import uuid

from fastapi import HTTPException, Request

from reply_agent.db.models import Business, User
from reply_agent.db.session import get_sessionmaker

_REDIRECT_TO_LOGIN = HTTPException(status_code=303, headers={"Location": "/login"})


async def get_current_user(request: Request) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise _REDIRECT_TO_LOGIN

    async with get_sessionmaker()() as session:
        user = await session.get(User, uuid.UUID(user_id))
    if user is None:
        # Stale session (e.g. the user row was deleted) — clear it rather than loop on it.
        request.session.clear()
        raise _REDIRECT_TO_LOGIN
    return user


async def require_business_access(request: Request, business_id: uuid.UUID) -> Business:
    """For routes where business_id is a path or query parameter — FastAPI resolves it from
    whichever scope the route itself declares it in, same as the endpoint function would.
    """
    user = await get_current_user(request)

    async with get_sessionmaker()() as session:
        business = await session.get(Business, business_id)

    # 404, not 403 — don't confirm to a logged-in user that some other business_id exists.
    if business is None or user.business_id != business_id:
        raise HTTPException(status_code=404, detail="Business not found")
    return business


async def ensure_business_access(request: Request, business_id: uuid.UUID) -> None:
    """Same check as require_business_access, for POST routes where business_id arrives inside
    a JSON body instead — FastAPI dependencies can't see into a Pydantic body model, so those
    routes call this directly rather than via Depends(). No separate existence check needed:
    User.business_id is a CASCADE foreign key, so a live user row's business_id always points
    at a business that still exists.
    """
    user = await get_current_user(request)
    if user.business_id != business_id:
        raise HTTPException(status_code=404, detail="Business not found")
