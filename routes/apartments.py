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
from utils.models import Apartments, House_Units, Landlords, Tenants, Users

router = APIRouter()

READ_ONLY_FIELDS = {"id", "created_at", "created_by"}


def normalize_apartment_data(data: Dict) -> Dict:
    return {
        "name": data["name"].strip().upper(),
        "location": data["location"].strip().upper(),
        "landlord_id": data["landlord_id"].strip()
    }

     
async def get_landlords(    
    session: AsyncSession,
):
    stmt = (
        select(Landlords)
        .where(
            Landlords.status != "deleted"
        )
        .order_by(Landlords.name)
    )

    rows = (await session.execute(stmt)).scalars()

    landlords = [
        {
            "id": landlord.id,
            "name": landlord.name
        }
        for landlord in rows
    ]
    
    return landlords


async def update_apartment(
    session: AsyncSession,
    current_user: Users,
    apartment_id: str,
    updates: Dict,
    action: Optional[str] = 'updated'
) -> Tuple[Optional[str], Optional[str], Optional[Apartments]]:
    try:
        apartment_uuid = uuid.UUID(apartment_id)
    except ValueError:
        return None, "Invalid apartment ID", None

    try:
        result = await session.execute(
            select(Apartments).where(Apartments.id == apartment_uuid)
        )
        apartment = result.scalar_one_or_none()

        if not apartment:
            return None, f"Apartment `{apartment_id}` not found", None

        for field, value in updates.items():
            if field not in READ_ONLY_FIELDS:
                setattr(apartment, field, value)

        apartment.updated_by = current_user.id
        apartment.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(apartment)

        return f"Apartment `{apartment.name}` {action} successfully", None, apartment

    except Exception as exc:
        await session.rollback()
        return None, str(exc), None


async def get_apartments_data(    
    session: AsyncSession,
    landlord_id: str
):
    filters = [
        Apartments.status != "deleted",
        Landlords.status != "deleted"
    ]
    
    if landlord_id:    
        filters.append(Landlords.id == landlord_id)
    
    stmt = (
        select(
            Apartments,#
            Landlords.name.label("landlord"),
            func.count(House_Units.id).label("houses_count"),
            func.count(Tenants.id).label("tenants_count"),
        )
        .join(
            Landlords,
            Apartments.landlord_id == Landlords.id,
            isouter=True,
        )
        .join(
            House_Units,
            House_Units.apartment_id == Apartments.id,
            isouter=True,
        )
        .join(
            Tenants,
            Tenants.house_unit_id == House_Units.id,
            isouter=True,
        )
        .where(*filters)
        .group_by(Apartments.id)
        .group_by(Landlords.id)
        .order_by(Apartments.name)
    )


    rows = (await session.execute(stmt)).all()

    apartments = [
        {
            "id": apartment.id,
            "name": apartment.name,
            "location": apartment.location,
            "landlord": landlord,
            "houses": houses_count or 0,
            "tenants": tenants_count or 0,
        }
        for apartment, landlord, houses_count, tenants_count in rows
    ]

    # Count stats properly
    total_house_units = sum(a["houses"] for a in apartments)
    total_tenants = sum(a["tenants"] for a in apartments)

    stats = {
        "total_apartments": len(apartments),
        "total_house_units": total_house_units,
        "total_tenants": total_tenants,
    }
    
    landlords = await get_landlords(session)
    
    return apartments, stats, landlords

@router.get("/apartments", response_class=HTMLResponse)
async def list_apartments(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
    landlord_id: Annotated[str | None, Query()] = None,
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    
    if landlord_id:    
        try:
            landlord_id = uuid.UUID(landlord_id)            
        except ValueError:
            errors = "Invalid landlord ID"

    success = errors = None

    apartments, stats, landlords = await get_apartments_data(session, landlord_id)
    
    return templates.TemplateResponse(
        "apartments.html",
        {
            "request": request,
            "active": "apartments",
            "apartments": apartments,
            "stats": stats,
            "landlords": landlords,
            "landlord_id": landlord_id,
            "success": success,
            "errors": errors,
        },
    )


@router.post("/apartments", response_class=HTMLResponse)
async def delete_apartment(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
    landlord_id: Annotated[str | None, Query()] = None,
    delete_id: Optional[str] = Form(None),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    
    if landlord_id:    
        try:
            landlord_id = uuid.UUID(landlord_id)            
        except ValueError:
            errors = "Invalid landlord ID"

    success = errors = None
    
    if delete_id:
        success, errors, _ = await update_apartment(
            session, 
            current_user, 
            delete_id, 
            {"status": "deleted"},
            action='deleted'
        )
        
    apartments, stats, landlords = await get_apartments_data(session, landlord_id)

    return templates.TemplateResponse(
        "apartments.html",
        {
            "request": request,
            "active": "apartments",
            "apartments": apartments,
            "stats": stats,
            "landlords": landlords,
            "landlord_id": landlord_id,
            "success": success,
            "errors": errors,
        },
    )
    
@router.get("/new-apartment", response_class=HTMLResponse)
async def new_apartment_form(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    
    landlords = await get_landlords(session)
    
    return templates.TemplateResponse(
        "apartments-new.html",
        {
            "request": request, 
            "landlords": landlords,
            "active": "new_apartment"
        },
    )


@router.post("/new-apartment", response_class=HTMLResponse)
async def create_apartment(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
    name: str = Form(...),
    location: str = Form(...),
    landlord_id: str = Form(...)
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    data = normalize_apartment_data(locals())
    
    landlords = await get_landlords(session)
    
    now = datetime.utcnow()

    apartment = Apartments(
        **data,
        created_at=now,
        created_by=current_user.id,
    )

    try:
        session.add(apartment)
        await session.commit()

        return templates.TemplateResponse(
            "apartments-new.html",
            {
                "request": request,
                "landlords": landlords,
                "active": "new_apartment",
                "success": f"Apartment {apartment.name} created successfully",
                "errors": {},
                "form_data": {},
            },
        )

    except Exception as exc:
        await session.rollback()
        return templates.TemplateResponse(
            "apartments-new.html",
            {
                "request": request,
                "landlords": landlords,
                "active": "new_apartment",
                "errors": {"general": str(exc)},
                "form_data": locals(),
            },
        )


@router.get("/edit-apartment", response_class=HTMLResponse)
async def edit_apartment_form(
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
        apartment_id = uuid.UUID(id)
    except Exception:
        return templates.TemplateResponse(
            "apartments-edit.html",
            {
                "request": request,
                "active": "apartments",
                "errors": "Invalid apartment ID",
            },
        )
    
    landlords = await get_landlords(session)

    apartment = (
        await session.execute(select(Apartments).where(Apartments.id == apartment_id))
    ).scalar_one_or_none()

    if not apartment:
        return templates.TemplateResponse(
            "apartments-edit.html",
            {
                "request": request,
                "landlords": landlords,
                "active": "apartments",
                "errors": f"Apartment `{id}` not found",
            },
        )

    return templates.TemplateResponse(
        "apartments-edit.html",
        {
            "request": request,
            "landlords": landlords,
            "active": "apartments",
            "apartment": apartment,
        },
    )


@router.post("/edit-apartment", response_class=HTMLResponse)
async def edit_apartment(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
    id: Annotated[str | None, Query()] = None,
    name: str = Form(...),
    location: str = Form(...),
    landlord_id: str = Form(...)
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    data = normalize_apartment_data(locals())

    success, errors, apartment = await update_apartment(
        session,
        current_user,
        id,
        data,
    )
    
    landlords = await get_landlords(session)

    return templates.TemplateResponse(
        "apartments-edit.html",
        {
            "request": request,
            "landlords": landlords,
            "active": "apartments",
            "success": success,
            "errors": errors,
            "apartment": apartment,
        },
    )
