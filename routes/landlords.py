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
from utils.models import Apartments, Landlords, Licenses, Packages, Users

router = APIRouter()

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
PHONE_REGEX = re.compile(r"^\+?254[17]\d{8}$|^0[17]\d{8}$")
READ_ONLY_FIELDS = {"id", "created_at", "created_by"}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def validate_landlord_form(
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


def normalize_landlord_data(data: Dict) -> Dict:
    return {
        "name": data["name"].strip().upper(),
        "email": data["email"].strip().lower(),
        "phone": "254" + data["phone"].strip()[-9:],
        "id_number": data["id_number"].strip(),
        "kra_pin": (data.get("kra_pin") or "").strip().upper() or None,
        "address": (data.get("address") or "").strip().upper() or None,
        "bank_name": (data.get("bank_name") or "").strip().upper() or None,
        "bank_account": (data.get("bank_account") or "").strip().upper() or None,
        "commission_rate": data.get("commission_rate"),
    }


async def update_landlord(
    session: AsyncSession,
    current_user: Users,
    landlord_id: str,
    updates: Dict,
) -> Tuple[Optional[str], Optional[str], Optional[Landlords]]:
    try:
        landlord_uuid = uuid.UUID(landlord_id)
    except ValueError:
        return None, "Invalid landlord ID", None

    try:
        result = await session.execute(
            select(Landlords).where(Landlords.id == landlord_uuid)
        )
        landlord = result.scalar_one_or_none()

        if not landlord:
            return None, f"Landlord `{landlord_id}` not found", None

        if updates.pop("toggle_status", False):
            landlord.status = "inactive" if landlord.status == "active" else "active"
        else:
            for field, value in updates.items():
                if field not in READ_ONLY_FIELDS:
                    setattr(landlord, field, value)

        landlord.updated_by = current_user.id
        landlord.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(landlord)

        return f"Landlord `{landlord.name}` updated successfully", None, landlord

    except Exception as exc:
        await session.rollback()
        return None, str(exc), None


# ─────────────────────────────────────────────
# List Landlords
# ─────────────────────────────────────────────
@router.get("/landlords", response_class=HTMLResponse)
async def list_landlords(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
    toggle_status_id: Annotated[str | None, Query()] = None,
    delete_id: Annotated[str | None, Query()] = None,
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    current_user = current_user
    success = errors = None

    if toggle_status_id:
        success, errors, _ = await update_landlord(
            session, current_user, toggle_status_id, {"toggle_status": True}
        )

    if delete_id:
        success, errors, _ = await update_landlord(
            session, current_user, delete_id, {"status": "deleted"}
        )

    stmt = (
        select(Landlords, func.count(Apartments.id))
        .join(Apartments, Apartments.landlord_id == Landlords.id, isouter=True)
        .where(
            Landlords.status != "deleted",
            Apartments.status != "deleted"
        )
        .group_by(Landlords.id)
        .order_by(Landlords.name)
    )

    rows = (await session.execute(stmt)).all()

    landlords = [
        {
            "id": landlord.id,
            "name": landlord.name,
            "email": landlord.email,
            "phone": landlord.phone,
            "id_number": landlord.id_number,
            "status": landlord.status,
            "apartments": count or 0,
        }
        for landlord, count in rows
    ]

    status_counts = Counter(l["status"] for l in landlords)
    apt_counts = Counter("with" if l["apartments"] else "without" for l in landlords)

    stats = {
        "total_landlords": len(landlords),
        "active_landlords": status_counts.get("active", 0),
        "inactive_landlords": status_counts.get("inactive", 0),
        "with_properties": apt_counts["with"],
        "without_properties": apt_counts["without"],
    }

    return templates.TemplateResponse(
        "landlords.html",
        {
            "request": request,
            "active": "landlords",
            "landlords": landlords,
            "stats": stats,
            "success": success,
            "errors": errors,
        },
    )


# ─────────────────────────────────────────────
# New Landlord
# ─────────────────────────────────────────────
@router.get("/new-landlord", response_class=HTMLResponse)
async def new_landlord_form(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    return templates.TemplateResponse(
        "landlords-new.html",
        {"request": request, "active": "new_landlord"},
    )


@router.post("/new-landlord", response_class=HTMLResponse)
async def create_landlord(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    id_number: str = Form(...),
    kra_pin: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    bank_name: Optional[str] = Form(None),
    bank_account: Optional[str] = Form(None),
    commission_rate: Optional[float] = Form(None),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    errors = validate_landlord_form(name, email, phone, id_number, commission_rate)
    if errors:
        return templates.TemplateResponse(
            "landlords-new.html",
            {
                "request": request,
                "active": "new_landlord",
                "errors": errors,
                "form_data": locals(),
            },
        )

    data = normalize_landlord_data(locals())
    now = datetime.utcnow()

    landlord = Landlords(
        **data,
        created_at=now,
        created_by=current_user.id,
    )

    trial_package = (
        await session.execute(select(Packages).where(Packages.name == "TRIAL"))
    ).scalar_one()

    license = Licenses(
        key=str(uuid.uuid4()).upper(),
        package_id=trial_package.id,
        landlord_id=landlord.id,
        expires_at=now + timedelta(days=trial_package.validity),
        created_at=now,
        created_by=current_user.id,
    )

    try:
        session.add_all([landlord, license])
        await session.commit()

        return templates.TemplateResponse(
            "landlords-new.html",
            {
                "request": request,
                "active": "new_landlord",
                "success": f"Landlord {landlord.name} created successfully",
                "errors": {},
                "form_data": {},
            },
        )

    except Exception as exc:
        await session.rollback()
        return templates.TemplateResponse(
            "landlords-new.html",
            {
                "request": request,
                "active": "new_landlord",
                "errors": {"general": str(exc)},
                "form_data": locals(),
            },
        )


# ─────────────────────────────────────────────
# Edit Landlord
# ─────────────────────────────────────────────
@router.get("/edit-landlord", response_class=HTMLResponse)
async def edit_landlord_form(
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
        landlord_id = uuid.UUID(id)
    except Exception:
        return templates.TemplateResponse(
            "landlords-edit.html",
            {
                "request": request,
                "active": "landlords",
                "errors": "Invalid landlord ID",
            },
        )

    landlord = (
        await session.execute(select(Landlords).where(Landlords.id == landlord_id))
    ).scalar_one_or_none()

    if not landlord:
        return templates.TemplateResponse(
            "landlords-edit.html",
            {
                "request": request,
                "active": "landlords",
                "errors": f"Landlord `{id}` not found",
            },
        )

    return templates.TemplateResponse(
        "landlords-edit.html",
        {
            "request": request,
            "active": "landlords",
            "landlord": landlord,
        },
    )


@router.post("/edit-landlord", response_class=HTMLResponse)
async def edit_landlord(
    request: Request,
    current_user: Annotated[
        Users | RedirectResponse, Depends(get_current_user)
    ],
    session: AsyncSession = Depends(get_session),
    id: Annotated[str | None, Query()] = None,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    id_number: str = Form(...),
    kra_pin: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    bank_name: Optional[str] = Form(None),
    bank_account: Optional[str] = Form(None),
    commission_rate: Optional[float] = Form(None),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    errors = validate_landlord_form(name, email, phone, id_number, commission_rate)
    if errors:
        return templates.TemplateResponse(
            "landlords-edit.html",
            {
                "request": request,
                "active": "landlords",
                "errors": errors,
            },
        )

    data = normalize_landlord_data(locals())

    success, errors, landlord = await update_landlord(
        session,
        current_user,
        id,
        data,
    )

    return templates.TemplateResponse(
        "landlords-edit.html",
        {
            "request": request,
            "active": "landlords",
            "success": success,
            "errors": errors,
            "landlord": landlord,
        },
    )
