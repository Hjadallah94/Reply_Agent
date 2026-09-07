"""Signup, login, logout for the dashboard. One user per business at signup time (multiple
staff accounts can be added later — nothing in the data model prevents it, there's just no UI
for it yet). Session-based via Starlette's signed-cookie middleware (app.py), not a server-side
session table or JWT — simplest thing that actually works for a single-service monolith.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from reply_agent.auth.security import hash_password, verify_password
from reply_agent.billing.tiers import tier_comparison_rows
from reply_agent.db.models import Business, PlanTier, User
from reply_agent.db.session import get_sessionmaker

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _tier_row(value: str) -> dict:
    """Doc 3 roadmap (real tier differentiation, 2026-09-07) — looks up one row of
    tier_comparison_rows() by its PlanTier.value, for re-rendering signup.html's account-creation
    form (with its "you're signing up for" banner) after a validation error. Callers only pass an
    already-PlanTier-validated value, so the row is always found.
    """
    return next(row for row in tier_comparison_rows() if row["value"] == value)


@router.get("/signup")
async def signup_page(request: Request, tier: str | None = None):
    """Doc 3 roadmap (real tier differentiation, 2026-09-07) — plan-first signup: no `tier` query
    param renders the 3-tier comparison (Zoko-style), picking a plan links to this same route
    with `?tier=<tier>` to render the actual account-creation form. Kept as one route/template
    rather than two so "change plan" can link straight back to the bare comparison.
    """
    if tier is None:
        return templates.TemplateResponse(
            request, "signup.html", {"error": None, "tiers": tier_comparison_rows(), "tier": None}
        )

    try:
        chosen_tier = PlanTier(tier)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Unknown plan") from exc

    return templates.TemplateResponse(
        request, "signup.html", {"error": None, "tiers": None, "tier": _tier_row(chosen_tier.value)}
    )


@router.post("/signup")
async def signup_submit(
    request: Request,
    business_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    tier: str = Form(...),
    whatsapp_number: str = Form(""),
    accept_terms: bool = Form(False),
):
    business_name = business_name.strip()
    email = email.strip().lower()
    whatsapp_number = whatsapp_number.strip()

    try:
        plan_tier = PlanTier(tier)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid plan tier") from exc

    if not business_name or not email or len(password) < 8:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {
                "error": "Business name, a valid email, and a password of at least 8 characters.",
                "tiers": None,
                "tier": _tier_row(tier),
            },
            status_code=400,
        )

    if not accept_terms:
        return templates.TemplateResponse(
            request,
            "signup.html",
            {
                "error": "You must agree to the Terms of Service and Privacy Policy to sign up.",
                "tiers": None,
                "tier": _tier_row(tier),
            },
            status_code=400,
        )

    async with get_sessionmaker()() as session:
        business = Business(
            name=business_name,
            plan_tier=plan_tier,
            requested_whatsapp_number=whatsapp_number or None,
        )
        session.add(business)
        await session.flush()

        user = User(
            business_id=business.id,
            email=email,
            password_hash=hash_password(password),
            accepted_terms_at=datetime.now(UTC),
        )
        session.add(user)

        try:
            await session.commit()
        except IntegrityError:
            return templates.TemplateResponse(
                request,
                "signup.html",
                {
                    "error": "That email is already registered.",
                    "tiers": None,
                    "tier": _tier_row(tier),
                },
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
