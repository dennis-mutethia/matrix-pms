
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
from core.templating import templates

from utils.database import get_session
from utils.helper_auth import get_current_user_or_redirect
from utils.models import Users

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(
    request: Request,
    current_user_or_redirect: Annotated[Users | RedirectResponse, Depends(get_current_user_or_redirect)],
    session: AsyncSession = Depends(get_session)  # still available if needed
):
    if isinstance(current_user_or_redirect, RedirectResponse):
        return current_user_or_redirect

    user: Users = current_user_or_redirect

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "active": "dashboard",
            "user": user,
        }
    )