import re

from fastapi import APIRouter, Request, Form, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.templating import templates
from utils.database import get_session
from utils.models import Users
from utils.helper_auth import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, hash_password 

router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
async def get_login(
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    return templates.TemplateResponse(
        "login.html",          
        {
            "request": request
        }
    )
    
@router.post("/login", response_class=HTMLResponse)
async def post_login(
    request: Request,
    response: Response,                     # ← very important!
    session: AsyncSession = Depends(get_session),
    phone: str = Form(...),
    password: str = Form(...)
):
    errors = {}

    # Basic validation
    phone = phone.strip()
    if not phone:
        errors["phone"] = "Phone number is required"
    elif not re.match(r"^(?:\+254|0)[17]\d{8}$", phone):
        errors["phone"] = "Invalid Kenyan phone format (e.g. +2547XXXXXXXX or 07XXXXXXXX)"

    if not password.strip():
        errors["password"] = "Password is required"

    if errors:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "errors": errors}
        )

    try:
        phone = "254" + phone[-9:]

        stmt = select(Users).where(Users.phone == phone)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            errors["phone"] = f"User with phone {phone} does not exist"

        elif hash_password(password) != user.password:
            errors["password"] = "Incorrect password"

        if errors:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "errors": errors}
            )

        # Success → create token
        access_token = create_access_token(data={"sub": str(user.id)})
        
        # Create redirect FIRST, then set cookie ON IT
        redirect = RedirectResponse(
            url="/dashboard",
            status_code=status.HTTP_303_SEE_OTHER
        )
        redirect.set_cookie(
            key="access_token",             # must match what get_current_user reads
            value=access_token,
            httponly=True,
            secure=False,                   # ← crucial for http://localhost
            samesite="lax",
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
        return redirect


    except Exception as exc:
        # In production: log the error, don't show to user
        print(f"Login error: {exc}")           # replace with proper logging
        errors["general"] = "An error occurred. Please try again."
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "errors": errors}
        )