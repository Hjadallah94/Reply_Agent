"""Signup, login, logout for the dashboard. One user per business at signup time (multiple
staff accounts can be added later — nothing in the data model prevents it, there's just no UI
for it yet). Session-based via Starlette's signed-cookie middleware (app.py), not a server-side
session table or JWT — simplest thing that actually works for a single-service monolith.
"""

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from reply_agent.auth.security import hash_password, verify_password
from reply_agent.db.models import Business, PlanTier, User
from reply_agent.db.session import get_sessionmaker

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


@router.get("/signup")
async def signup_page(request: Request):
    return templates.TemplateResponse(request, "signup.html", {"error": None})


@router.post("/signup")
async def signup_submit(
    request: Request,
    business_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    business_name = business_name.strip()
    email = email.strip().lower()

    if not business_name or not email or len(password) < 8:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {"error": "Business name, a valid email, and a password of at least 8 characters."},
            status_code=400,
        )

    async with get_sessionmaker()() as session:
        business = Business(name=business_name, plan_tier=PlanTier.starter)
        session.add(business)
        await session.flush()

        user = User(business_id=business.id, email=email, password_hash=hash_password(password))
        session.add(user)

        try:
            await session.commit()
        except IntegrityError:
            return templates.TemplateResponse(
                request,
                "signup.html",
                {"error": "That email is already registered."},
                status_code=400,
            )

        user_id, business_id = str(user.id), str(business.id)

    request.session["user_id"] = user_id
    return RedirectResponse(url=f"/businesses/{business_id}/dashboard", status_code=303)


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()

    async with get_sessionmaker()() as session:
        user = await session.scalar(select(User).where(User.email == email))

    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Incorrect email or password."},
            status_code=400,
        )

    request.session["user_id"] = str(user.id)
    return RedirectResponse(url=f"/businesses/{user.business_id}/dashboard", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
