import re
import uuid
from datetime import datetime
from typing import Annotated, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, Form, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func

from core.templating import templates
from utils.database import get_session
from utils.helper_auth import get_current_user
from utils.models import Apartments, House_Units, Tenants, Users

router = APIRouter()

READ_ONLY_FIELDS = {"id", "created_at", "created_by"}


def normalize_house_unit_data(data: Dict) -> Dict:
    return {
        "name": data["name"].strip().upper(),
        "apartment_id": data["apartment_id"].strip(),
        "rent": data["rent"],
        "rent_deposit": data["rent_deposit"],
        "water_deposit": data["water_deposit"],
        "electricity_deposit": data["electricity_deposit"],
        "other_deposits": data["other_deposits"]
    }
    
        
async def get_apartments(    
    session: AsyncSession,
    current_user: Users
):
    stmt = (
        select(Apartments)
        .where(
            Apartments.status != "deleted",
            Apartments.landlord_id == current_user.landlord_id
        )
        .order_by(Apartments.name)
    )

    rows = (await session.execute(stmt)).scalars()

    apartments = [
        {
            "id": apartment.id,
            "name": apartment.name
        }
        for apartment in rows
    ]
    
    return apartments

async def update_house_unit(
    session: AsyncSession,
    current_user: Users,
    house_unit_id: str,
    updates: Dict,
) -> Tuple[Optional[str], Optional[str], Optional[Apartments]]:
    try:
        house_unit_uuid = uuid.UUID(house_unit_id)
    except ValueError:
        return None, "Invalid house_unit ID", None

    try:
        result = await session.execute(
            select(House_Units).where(House_Units.id == house_unit_uuid)
        )
        house_unit = result.scalar_one_or_none()

        if not house_unit:
            return None, f"House Unit `{house_unit_id}` not found", None

        for field, value in updates.items():
            if field not in READ_ONLY_FIELDS:
                setattr(house_unit, field, value)

        house_unit.updated_by = current_user.id
        house_unit.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(house_unit)

        return f"House Unit `{house_unit.name}` updated successfully", None, house_unit

    except Exception as exc:
        await session.rollback()
        return None, str(exc), None


@router.get("/house-units", response_class=HTMLResponse)
async def list_house_units(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
    delete_id: Annotated[str | None, Query()] = None,
    apartment_id: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    success = errors = None

    if delete_id:
        success, errors, _ = await update_house_unit(
            session, current_user, delete_id, {"status": "deleted"}
        )
        
    filters = [
        House_Units.status != "deleted",
        Apartments.landlord_id == current_user.landlord_id,
    ]

    if apartment_id:    
        try:
            apartment_id = uuid.UUID(apartment_id)
            filters.append(House_Units.apartment_id == apartment_id)
        except ValueError:
            errors = "Invalid apartment ID"

    if status:
        filters.append(
            Tenants.id.is_(None) if status == "vacant" else Tenants.id.is_not(None)
        )
    
    stmt = (
        select(
            House_Units,
            Apartments.name.label("apartment"),
            Tenants.name.label("tenant")
        )
        .join(Apartments, House_Units.apartment_id == Apartments.id)
        .join(Tenants, Tenants.house_unit_id == House_Units.id, isouter=True)
        .where(*filters)
        .order_by(House_Units.name)
    )
    
    rows = (await session.execute(stmt)).all()

    house_units = [
        {
            "id": house_unit.id,
            "name": house_unit.name,
            "apartment": apartment,
            "tenant": tenant,
            "rent": f"{house_unit.rent:,.0f}",
            "rent_deposit": f"{house_unit.rent_deposit:,.0f}",
            "water_deposit": f"{house_unit.water_deposit:,.0f}",
            "electricity_deposit": f"{house_unit.electricity_deposit:,.0f}",
            "other_deposits": f"{house_unit.other_deposits:,.0f}"
        }
        for house_unit, apartment, tenant in rows
    ]
    
    apartments = await get_apartments(session, current_user)
       
    return templates.TemplateResponse(
        "house-units.html",
        {
            "request": request,
            "active": "house_units",
            "house_units": house_units,
            "apartments": apartments,
            "apartment_id": apartment_id,
            "status": status,
            "success": success,
            "errors": errors,
        },
    )


@router.get("/new-house-unit", response_class=HTMLResponse)
async def new_house_unit_form(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    
    apartments = await get_apartments(session, current_user)
    
    return templates.TemplateResponse(
        "house-units-new.html",
        {
            "request": request, 
            "apartments": apartments,
            "active": "new_house_unit"
        },
    )


@router.post("/new-house-unit", response_class=HTMLResponse)
async def create_house_unit(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
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
    now = datetime.utcnow()

    house_unit = House_Units(
        **data,
        created_at=now,
        created_by=current_user.id,
    )

    try:
        session.add(house_unit)
        await session.commit()

        return templates.TemplateResponse(
            "house-units-new.html",
            {
                "request": request,
                "active": "new_house_unit",
                "success": f"House Unit {house_unit.name} created successfully",
                "errors": {},
                "form_data": {},
            },
        )

    except Exception as exc:
        await session.rollback()
        return templates.TemplateResponse(
            "house-units-new.html",
            {
                "request": request,
                "active": "new_house_unit",
                "errors": {"general": str(exc)},
                "form_data": locals(),
            },
        )


@router.get("/edit-house-unit", response_class=HTMLResponse)
async def edit_house_unit_form(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
    id: Annotated[str | None, Query()] = None,
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    try:
        house_unit_id = uuid.UUID(id)
    except Exception:
        return templates.TemplateResponse(
            "house-units-edit.html",
            {
                "request": request,
                "active": "house_units",
                "errors": "Invalid house_unit ID",
            },
        )

    house_unit = (
        await session.execute(select(House_Units).where(House_Units.id == house_unit_id))
    ).scalar_one_or_none()

    if not house_unit:
        return templates.TemplateResponse(
            "house-units-edit.html",
            {
                "request": request,
                "active": "house_units",
                "errors": f"House Unit `{id}` not found",
            },
        )

    apartments = await get_apartments(session, current_user)
    
    return templates.TemplateResponse(
        "house-units-edit.html",
        {
            "request": request,
            "active": "house_units",
            "house_unit": house_unit,
            "apartments": apartments
        },
    )


@router.post("/edit-house-unit", response_class=HTMLResponse)
async def edit_house_unit(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
    id: Annotated[str | None, Query()] = None,         
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
    
    success, errors, house_unit = await update_house_unit(
        session,
        current_user,
        id,
        data,
    )
    
    apartments = await get_apartments(session, current_user)

    return templates.TemplateResponse(
        "house-units-edit.html",
        {
            "request": request,
            "active": "house_units",
            "success": success,
            "errors": errors,
            "house_unit": house_unit,
            "apartments": apartments
        },
    )
