
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select
from core.templating import templates

from utils.database import get_session
from utils.helpers import require_user
from utils.models import Users
from utils.models import Apartments, House_Units, Landlords, Tenants

router = APIRouter()


@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session)  # still available if needed
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    
    stmt = select(
        select(func.count()).select_from(Landlords).where(Landlords.status != "deleted").scalar_subquery(),
        select(func.count()).select_from(Apartments).where(Apartments.status != "deleted").scalar_subquery(),
        select(func.count()).select_from(House_Units).where(House_Units.status != "deleted").scalar_subquery(),
        select(func.count()).select_from(Tenants).where(Tenants.status != "deleted").scalar_subquery(),
    )

    landlords, apartments, house_units, tenants = (await session.execute(stmt)).one()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "active": "dashboard",
            "landlords": landlords,
            "apartments": apartments,
            "house_units": house_units,
            "tenants": tenants
        }
    )