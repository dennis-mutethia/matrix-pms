import re

from fastapi import APIRouter, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.templating import templates
from utils.database import get_session
from utils.models import Users
from utils.helper_auth import (
    create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    hash_password,
)

router = APIRouter()

KENYAN_PHONE_REGEX = re.compile(r"^(?:\+254|0)[17]\d{8}$")


def normalize_phone(phone: str) -> str:
    """Convert phone to 2547XXXXXXXX format."""
    return "254" + phone[-9:]


def validate_login_form(phone: str, password: str) -> dict:
    errors = {}

    phone = phone.strip()
    password = password.strip()

    if not phone:
        errors = "Phone number is required"
    elif not KENYAN_PHONE_REGEX.match(phone):
        errors = "Invalid Kenyan phone format (e.g. +2547XXXXXXXX or 07XXXXXXXX)"
        
    if not password:
        errors = "Password is required"

    return errors


def render_login(request: Request, errors: str = None):
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "errors": errors,
        },
    )


@router.get("/login", response_class=HTMLResponse)
async def get_login(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    return render_login(request)

@router.post("/login", response_class=HTMLResponse)
async def post_login(
    request: Request,
    phone: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    errors = validate_login_form(phone, password)
    if errors:
        return render_login(request, errors)

    try:
        phone = normalize_phone(phone)

        stmt = select(Users).where(Users.phone == phone)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return render_login(
                request,
                f"User with phone: `{phone}` does not exist",
            )

        if hash_password(password) != user.password:
            return render_login(
                request,
                "Incorrect password",
            )

        access_token = create_access_token(
            data={"sub": str(user.id)}
        )

        # 🔑 THIS is the missing piece
        next_url = request.query_params.get("next", "/dashboard")

        # 🛡️ prevent open redirects
        # if not next_url.startswith("/"):
        #     next_url = "/dashboard"

        redirect = RedirectResponse(
            url=next_url,
            status_code=status.HTTP_303_SEE_OTHER,
        )
        redirect.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        return redirect

    except Exception:
        return render_login(
            request,
            "An error occurred. Please try again.",
        )
