
import logging, uuid
from datetime import datetime
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select
from typing import Annotated

from core.templating import READ_ONLY_FIELDS, templates
from utils.database import get_session
from utils.helpers import get_landlords, require_user
from utils.models import Apartments, House_Units, Landlords, Occupancy, Users

logger = logging.getLogger(__name__)

router = APIRouter()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def parse_uuid(value: Optional[str], error_msg: str) -> Tuple[Optional[uuid.UUID], Optional[str]]:
    if not value:
        return None, None
    try:
        return uuid.UUID(value), None
    except ValueError as exc:
        logger.error(exc)
        return None, error_msg


def normalize_apartment_data(
    name: str,
    location: str,
    landlord_id: str,
    water_unit_rate: float, 
    garbage_charge: float, 
    service_charge: float
) -> Dict:
    return {
        "name": name.strip().upper(),
        "location": location.strip().upper(),
        "landlord_id": landlord_id,
        "water_unit_rate": water_unit_rate,
        "garbage_charge": garbage_charge,
        "service_charge": service_charge
    }


async def update_apartment(
    session: AsyncSession,
    current_user: Users,
    apartment_id: str,
    updates: Dict,
    action: str = "updated",
) -> Tuple[Optional[str], Optional[str], Optional[Apartments]]:

    apartment_uuid, error = parse_uuid(apartment_id, "Invalid apartment ID")
    if error:
        return None, error, None

    apartment = (
        await session.execute(
            select(Apartments).where(Apartments.id == apartment_uuid)
        )
    ).scalar_one_or_none()

    if not apartment:
        return None, f"Apartment `{apartment_id}` not found", None

    try:
        for field, value in updates.items():
            if field not in READ_ONLY_FIELDS:
                setattr(apartment, field, value)

        apartment.updated_by = current_user.id
        apartment.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(apartment)

        return f"Apartment `{apartment.name}` {action} successfully", None, apartment

    except Exception as exc:
        logger.error(exc)
        await session.rollback()
        return None, str(exc), None


# ------------------------------------------------------------------
# Renderers
# ------------------------------------------------------------------

async def render_apartments(
    request: Request,
    session: AsyncSession,
    landlord_id: Optional[uuid.UUID] = None,
    show_deleted: bool = False,
    success: Optional[str] = None,
    errors: Optional[str] = None,
):
    filters = []
    
    if not show_deleted:
        filters = [
            Apartments.status != "deleted",
            Landlords.status != "deleted",
        ]

    if landlord_id:
        filters.append(Landlords.id == landlord_id)

    stmt = (
        select(
            Apartments,
            Landlords,
            func.count(House_Units.id).label("houses"),
            func.count(Occupancy.id).label("tenants")
        )
        .join(Landlords, Apartments.landlord_id == Landlords.id, isouter=True)
        .join(House_Units, House_Units.apartment_id == Apartments.id, isouter=True)
        .join(Occupancy, Occupancy.house_unit_id == House_Units.id and Occupancy.end_date is None , isouter=True)
        .where(*filters)
        .group_by(Apartments.id, Landlords.id)
        .order_by(Apartments.name)
    )

    rows = (await session.execute(stmt)).all()

    apartments = [
        {
            "id": a.id,
            "name": a.name,
            "location": a.location,
            "status": a.status,
            "landlord": landlord,
            "houses": houses or 0,
            "tenants": tenants or 0,
        }
        for a, landlord, houses, tenants in rows
    ]

    stats = {
        "total_apartments": len(apartments),
        "total_house_units": sum(a["houses"] for a in apartments),
        "total_tenants": sum(a["tenants"] for a in apartments),
    }

    return templates.TemplateResponse(
        "apartments.html",
        {
            "request": request,
            "active": "apartments",
            "apartments": apartments,
            "stats": stats,
            "landlords": await get_landlords(session),
            "landlord_id": landlord_id,
            "success": success,
            "errors": errors,
        },
    )


async def render_new_apartment(
    request: Request,
    session: AsyncSession,
    success: Optional[str] = None,
    errors: Optional[str] = None,
):
    return templates.TemplateResponse(
        "apartments-new.html",
        {
            "request": request,
            "active": "new_apartment",
            "landlords": await get_landlords(session),
            "success": success,
            "errors": errors,
        },
    )


async def render_edit_apartment(
    request: Request,
    session: AsyncSession,
    apartment_id: uuid.UUID,
    success: Optional[str] = None,
    errors: Optional[str] = None,
):
    apartment = (
        await session.execute(
            select(Apartments).where(Apartments.id == apartment_id)
        )
    ).scalar_one_or_none()

    if not apartment:
        errors = "Apartment not found"

    return templates.TemplateResponse(
        "apartments-edit.html",
        {
            "request": request,
            "active": "apartments",
            "landlords": await get_landlords(session),
            "apartment": apartment,
            "success": success,
            "errors": errors,
        },
    )


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.get("/apartments", response_class=HTMLResponse)
async def fetch(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],    
    session: AsyncSession = Depends(get_session),
    landlord_id: Optional[str] = Query(None),
    show_deleted: bool = Query(False),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    landlord_uuid, errors = parse_uuid(landlord_id, "Invalid landlord ID")

    return await render_apartments(request, session, landlord_uuid, show_deleted, errors=errors)


@router.post("/apartments", response_class=HTMLResponse)
async def post(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
    landlord_id: Optional[str] = Query(None),
    show_deleted: bool = Query(False),
    delete_id: Optional[str] = Form(None),
    restore_id: Optional[str] = Form(None),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    landlord_uuid, errors = parse_uuid(landlord_id, "Invalid landlord ID")

    success = None
        
    if delete_id or restore_id:
        success, errors, _ = await update_apartment(
            session,
            current_user,
            delete_id if delete_id else restore_id,
            {
                "status": "deleted" if delete_id else 'active'
            },
            "deleted" if delete_id else 'restored'
        )

    return await render_apartments(request, session, landlord_uuid, show_deleted, success, errors)


@router.get("/apartments/new", response_class=HTMLResponse)
async def new_apartment_form(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    return await render_new_apartment(request, session)


@router.post("/apartments/new", response_class=HTMLResponse)
async def create_apartment(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
    name: str = Form(...),
    location: str = Form(...),
    landlord_id: str = Form(...),
    water_unit_rate: float = Form(...),
    garbage_charge: float = Form(...),
    service_charge: float = Form(...),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    
    apartment = Apartments(
        **normalize_apartment_data(name, location, landlord_id, water_unit_rate, garbage_charge, service_charge),
        created_at=datetime.utcnow(),
        created_by=current_user.id,
    )

    try:
        session.add(apartment)
        await session.commit()
        return await render_new_apartment(
            request,
            session,
            success=f"Apartment `{apartment.name}` created successfully",
        )
    except Exception as exc:
        logger.error(exc)
        await session.rollback()
        return await render_new_apartment(request, session, errors=str(exc))


@router.get("/apartments/edit/{id}", response_class=HTMLResponse)
async def edit_apartment_form(
    request: Request,    
    id: str,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    apartment_id, errors = parse_uuid(id, "Invalid apartment ID")
    if errors:
        return await render_apartments(request, session, errors=errors)

    return await render_edit_apartment(request, session, apartment_id)


@router.post("/apartments/edit/{id}", response_class=HTMLResponse)
async def edit_apartment(
    request: Request,
    id: str,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
    name: str = Form(...),
    location: str = Form(...),
    landlord_id: str = Form(...),
    water_unit_rate: float = Form(...),
    garbage_charge: float = Form(...),
    service_charge: float = Form(...),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    success, errors, _ = await update_apartment(
        session,
        current_user,
        id,
        normalize_apartment_data(name, location, landlord_id, water_unit_rate, garbage_charge, service_charge)
    )

    apartment_id, _ = parse_uuid(id, "")
    return await render_edit_apartment(request, session, apartment_id, success, errors)
