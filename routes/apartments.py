import re
import uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Annotated, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, Form, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func

from core.templating import templates
from utils.database import get_session
from utils.helper_auth import get_current_user
from utils.models import Apartments, House_Units, Landlords, Licenses, Packages, Users

router = APIRouter()

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
PHONE_REGEX = re.compile(r"^\+?254[17]\d{8}$|^0[17]\d{8}$")
READ_ONLY_FIELDS = {"id", "created_at", "created_by"}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def validate_apartment_form(
    name: str,
    email: str,
    phone: str,
    id_number: str,
    commission_rate: Optional[float],
) -> Dict[str, str]:
    errors = {}

    if not name.strip():
        errors["name"] = "Name is required"

    if "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Please enter a valid email address"

    if not id_number.strip():
        errors["id_number"] = "ID Number is required"

    if phone and not PHONE_REGEX.match(phone):
        errors["phone"] = "Invalid phone number format"

    if commission_rate is not None and not (0 <= commission_rate <= 100):
        errors["commission_rate"] = "Commission rate must be between 0 and 100"

    return errors


def normalize_apartment_data(data: Dict) -> Dict:
    return {
        "name": data["name"].strip().upper(),
        "location": data["location"].strip().upper(),
        "landlord_id": uuid.UUID(data["landlord_id"].strip())
    }


async def update_apartment(
    session: AsyncSession,
    current_user: Users,
    apartment_id: str,
    updates: Dict,
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

        return f"Apartment `{apartment.name}` updated successfully", None, apartment

    except Exception as exc:
        await session.rollback()
        return None, str(exc), None


# ─────────────────────────────────────────────
# List Apartments
# ─────────────────────────────────────────────
@router.get("/apartments", response_class=HTMLResponse)
async def list_apartments(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
    delete_id: Annotated[str | None, Query()] = None,
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    current_user = current_user
    success = errors = None

    if delete_id:
        success, errors, _ = await update_apartment(
            session, current_user, delete_id, {"status": "deleted"}
        )

    stmt = (
        select(Apartments, func.count(House_Units.id).label("houses_count"))
        .join(House_Units, House_Units.apartment_id == Apartments.id, isouter=True)
        .where(Apartments.status != "deleted")
        .group_by(Apartments.id)
        .order_by(Apartments.name)
    )

    rows = (await session.execute(stmt)).all()

    apartments = [
        {
            "id": apartment.id,
            "name": apartment.name,
            "location": apartment.location,
            "houses": houses_count or 0,
        }
        for apartment, houses_count in rows
    ]

    # Count stats properly
    total_house_units = sum(a["houses"] for a in apartments)
    #vacant_house_units = sum(1 for a in apartments if a["houses"] == 0)

    stats = {
        "total_apartments": len(apartments),
        "total_house_units": total_house_units,
        # "vacant_house_units": vacant_house_units,
        # If you have tenants info, you can add total_tenants here
        # "total_tenants": sum(a["tenants"] for a in apartments)
    }
    
    return templates.TemplateResponse(
        "apartments.html",
        {
            "request": request,
            "active": "apartments",
            "apartments": apartments,
            "stats": stats,
            "success": success,
            "errors": errors,
        },
    )


# ─────────────────────────────────────────────
# New Apartment
# ─────────────────────────────────────────────
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

    
    stmt = (
        select(Landlords)
        .where(Landlords.status != "deleted")
        .order_by(Landlords.name)
    )

    result = await session.execute(stmt)
    rows = result.scalars().all()  

    landlords = [
        {
            "id": landlord.id,
            "name": landlord.name
        }
        for landlord in rows
    ]
    
    return templates.TemplateResponse(
        "apartments-new.html",
        {
            "request": request, 
            "active": "new_apartment",
            "landlords": landlords
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
                "active": "new_apartment",
                "errors": {"general": str(exc)},
                "form_data": locals(),
            },
        )


# ─────────────────────────────────────────────
# Edit Apartment
# ─────────────────────────────────────────────
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

    apartment = (
        await session.execute(select(Apartments).where(Apartments.id == apartment_id))
    ).scalar_one_or_none()

    if not apartment:
        return templates.TemplateResponse(
            "apartments-edit.html",
            {
                "request": request,
                "active": "apartments",
                "errors": f"Apartment `{id}` not found",
            },
        )

    return templates.TemplateResponse(
        "apartments-edit.html",
        {
            "request": request,
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
    location: str = Form(...)
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

    return templates.TemplateResponse(
        "apartments-edit.html",
        {
            "request": request,
            "active": "apartments",
            "success": success,
            "errors": errors,
            "apartment": apartment,
        },
    )
