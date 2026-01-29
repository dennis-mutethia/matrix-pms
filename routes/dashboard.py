
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
from core.templating import templates

from utils.database import get_session
from utils.helper_auth import get_current_user
from utils.models import Users

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(get_current_user)],
    session: AsyncSession = Depends(get_session)  # still available if needed
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    user: Users = current_user

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "active": "dashboard",
            "user": user,
        }
    )