import logging, uuid
from datetime import datetime
from typing import Annotated, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.templating import READ_ONLY_FIELDS, templates
from utils.database import get_session
from utils.helpers import get_apartments, get_landlords, require_user
from utils.models import Apartments, House_Units, Landlords, Tenants, Users

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def parse_uuid(value: Optional[str], error_msg: str) -> Tuple[Optional[uuid.UUID], Optional[str]]:
    if not value:
        return None, None
    try:
        return uuid.UUID(value), None
    except ValueError as exc:
        logger.error(exc)
        return None, error_msg


def normalize_house_unit_data(data: Dict) -> Dict:
    return {
        "name": data["name"].strip().upper(),
        "apartment_id": data["apartment_id"],
        "rent": data["rent"],
        "rent_deposit": data["rent_deposit"],
        "water_deposit": data.get("water_deposit") or 0,
        "electricity_deposit": data.get("electricity_deposit") or 0,
        "other_deposits": data.get("other_deposits") or 0,
    }


async def update_house_unit(
    session: AsyncSession,
    current_user: Users,
    house_unit_id: str,
    updates: Dict,
    action: str = "updated",
) -> Tuple[Optional[str], Optional[str], Optional[House_Units]]:

    house_unit_uuid, error = parse_uuid(house_unit_id, "Invalid house unit ID")
    if error:
        return None, error, None

    house_unit = (
        await session.execute(
            select(House_Units).where(House_Units.id == house_unit_uuid)
        )
    ).scalar_one_or_none()

    if not house_unit:
        return None, f"House Unit `{house_unit_id}` not found", None

    try:
        for field, value in updates.items():
            if field not in READ_ONLY_FIELDS:
                setattr(house_unit, field, value)

        house_unit.updated_at = datetime.utcnow()
        house_unit.updated_by = current_user.id

        await session.commit()
        await session.refresh(house_unit)

        return f"House Unit `{house_unit.name}` {action} successfully", None, house_unit

    except Exception as exc:
        logger.error(exc)
        await session.rollback()
        return None, str(exc), None


# ─────────────────────────────────────────────
# Data Fetching
# ─────────────────────────────────────────────
async def get_house_units_data(
    session: AsyncSession,
    status: Optional[str],
    apartment_id: Optional[uuid.UUID],
    landlord_id: Optional[uuid.UUID],
    show_deleted: bool = False,
):
    filters = []
    if not show_deleted:
        filters = [
            House_Units.status != "deleted",
            Apartments.status != "deleted",
            Landlords.status != "deleted",
        ]

    if status:
        filters.append(
            Tenants.id.is_(None) if status == "vacant" else Tenants.id.is_not(None)
        )

    if apartment_id:
        filters.append(Apartments.id == apartment_id)

    if landlord_id:
        filters.append(Landlords.id == landlord_id)

    stmt = (
        select(
            House_Units,
            Apartments,
            Landlords,
            Tenants
        )
        .join(Apartments, House_Units.apartment_id == Apartments.id)
        .join(Landlords, Apartments.landlord_id == Landlords.id)
        .join(Tenants, Tenants.house_unit_id == House_Units.id and Tenants.status == 'occupied' , isouter=True)
        .where(*filters)
        .order_by(House_Units.name)
    )

    rows = (await session.execute(stmt)).all()

    house_units = [
        {
            "id": hu.id,
            "name": hu.name,
            "status": hu.status,
            "apartment": apartment,
            "landlord": landlord,
            "tenant": tenant,
            "rent": f"{hu.rent:,.0f}",
            "rent_deposit": f"{hu.rent_deposit:,.0f}",
            "water_deposit": f"{hu.water_deposit:,.0f}",
            "electricity_deposit": f"{hu.electricity_deposit:,.0f}",
            "other_deposits": f"{hu.other_deposits:,.0f}",
        }
        for hu, apartment, landlord, tenant in rows
    ]

    return (
        house_units,
        await get_apartments(session, landlord_id),
        await get_landlords(session),
    )


# ─────────────────────────────────────────────
# Renderers
# ─────────────────────────────────────────────
async def render_house_units(
    request: Request,
    session: AsyncSession,
    status: Optional[str],
    apartment_id: Optional[uuid.UUID],
    landlord_id: Optional[uuid.UUID],
    show_deleted: bool = Query(False),
    success: Optional[str] = None,
    errors: Optional[str] = None,
):
    house_units, apartments, landlords = await get_house_units_data(
        session, status, apartment_id, landlord_id, show_deleted
    )

    return templates.TemplateResponse(
        "house-units.html",
        {
            "request": request,
            "active": "house_units",
            "house_units": house_units,
            "apartments": apartments,
            "landlords": landlords,
            "apartment_id": apartment_id,
            "landlord_id": landlord_id,
            "status": status,
            "success": success,
            "errors": errors,
        },
    )


async def render_new_house_unit(
    request: Request,
    session: AsyncSession = Depends(get_session),
    success: Optional[str] = None,
    errors: Optional[Dict] = None,
    form_data: Optional[Dict] = None,
):
    return templates.TemplateResponse(
        "house-units-new.html",
        {
            "request": request,
            "active": "new_house_unit",
            "apartments": await get_apartments(session),
            "success": success,
            "errors": errors,
            "form_data": form_data or {},
        },
    )


async def render_edit_house_unit(
    request: Request,
    session: AsyncSession,
    house_unit_id: uuid.UUID,
    success: Optional[str] = None,
    errors: Optional[Dict] = None,
):
    house_unit = (
        await session.execute(
            select(House_Units).where(House_Units.id == house_unit_id)
        )
    ).scalar_one_or_none()

    if not house_unit:
        errors = "House Unit not found"

    return templates.TemplateResponse(
        "house-units-edit.html",
        {
            "request": request,
            "active": "house_units",
            "house_unit": house_unit,
            "apartments": await get_apartments(session),
            "success": success,
            "errors": errors
        },
    )


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────
@router.get("/house-units", response_class=HTMLResponse)
async def fetch(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
    landlord_id: Optional[str] = Query(None),
    apartment_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    show_deleted: bool = Query(False),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    landlord_uuid, err1 = parse_uuid(landlord_id, "Invalid landlord ID")
    apartment_uuid, err2 = parse_uuid(apartment_id, "Invalid apartment ID")

    return await render_house_units(
        request,
        session,
        status,
        apartment_uuid,
        landlord_uuid,
        show_deleted,
        errors=err1 or err2,
    )


@router.post("/house-units", response_class=HTMLResponse)
async def post(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
    landlord_id: Optional[str] = Query(None),
    apartment_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    delete_id: Optional[str] = Form(None),
    restore_id: Optional[str] = Form(None),
    show_deleted: bool = Query(False),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    landlord_uuid, err1 = parse_uuid(landlord_id, "Invalid landlord ID")
    apartment_uuid, err2 = parse_uuid(apartment_id, "Invalid apartment ID")

    success = errors = err1 or err2

    
    if (delete_id or restore_id) and not errors:
        success, errors, _ = await update_house_unit(
            session,
            current_user,
            delete_id if delete_id else restore_id,
            {"status": "deleted" if delete_id else "active"},
            "deleted" if delete_id else "restored",
        )
        
    return await render_house_units(
        request,
        session,
        status,
        apartment_uuid,
        landlord_uuid,
        show_deleted,
        success,
        errors,
    )


@router.get("/house-units/new", response_class=HTMLResponse)
async def new_house_unit_form(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    return await render_new_house_unit(request, session)


@router.post("/house-units/new", response_class=HTMLResponse)
async def create_house_unit(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
    name: str = Form(...),
    apartment_id: str = Form(...),
    rent: float = Form(...),
    rent_deposit: float = Form(...),
    water_deposit: Optional[float] = Form(None),
    electricity_deposit: Optional[float] = Form(None),
    other_deposits: Optional[float] = Form(None),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    success = errors = ''
    
    data = normalize_house_unit_data(locals())
    house_unit = House_Units(
        **data,
        created_at=datetime.utcnow(),
        created_by=current_user.id,
    )
    
    try:
        session.add(house_unit)
        await session.commit()
        success = f"House Unit `{house_unit.name}` created successfully"

    except Exception as exc:
        logger.error(exc)
        await session.rollback()
        errors = str(exc)        
    
    return await render_new_house_unit(
        request, 
        session, 
        success=success,
        errors=errors,
        form_data=locals()
    )
    

@router.get("/house-units/edit/{id}", response_class=HTMLResponse)
async def edit_house_unit_form(
    request: Request,
    id: str,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    
    house_unit_id, errors = parse_uuid(id, "Invalid house unit ID")

    return await render_edit_house_unit(
        request, 
        session, 
        house_unit_id, 
        errors=errors
    )
    

@router.post("/house-units/edit/{id}", response_class=HTMLResponse)
async def edit_house_unit(
    request: Request,
    id: str,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
    name: str = Form(...),
    apartment_id: str = Form(...),
    rent: float = Form(...),
    rent_deposit: float = Form(...),
    water_deposit: Optional[float] = Form(None),
    electricity_deposit: Optional[float] = Form(None),
    other_deposits: Optional[float] = Form(None),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    data = normalize_house_unit_data(locals())
    success, errors, _ = await update_house_unit(
        session,
        current_user,
        id,
        data
    )

    house_unit_id, _ = parse_uuid(id, "")
    return await render_edit_house_unit(
        request, 
        session, 
        house_unit_id, 
        success=success, 
        errors=errors
    )

