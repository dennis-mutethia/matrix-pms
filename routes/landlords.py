import logging, uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func

from core.templating import PHONE_REGEX, READ_ONLY_FIELDS, templates
from utils.database import get_session
from utils.helpers import require_user
from utils.models import Apartments, Landlords, Licenses, Packages, Users

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
        errors["email"] = "Invalid email address"

    if not id_number.strip():
        errors["id_number"] = "ID Number is required"
        
    if not phone.strip():
        errors["phone"] = "phone Number is required"

    if phone and not PHONE_REGEX.match(phone):
        errors["phone"] = "Invalid phone number format"

    if commission_rate is not None and not (0 <= commission_rate <= 100):
        errors["commission_rate"] = "Commission rate must be between 0 and 100"

    return errors


def normalize_landlord_data(
    name: str,
    email: str,
    phone: str,
    id_number: str,
    kra_pin: Optional[str],
    address: Optional[str],
    bank_name: Optional[str],
    bank_account: Optional[str],
    commission_rate: Optional[float],
) -> Dict:
    return {
        "name": name.strip().upper(),
        "email": email.strip().lower(),
        "phone": "254" + phone.strip()[-9:],
        "id_number": id_number.strip(),
        "kra_pin": kra_pin.strip().upper() if kra_pin else None,
        "address": address.strip().upper() if address else None,
        "bank_name": bank_name.strip().upper() if bank_name else None,
        "bank_account": bank_account.strip().upper() if bank_account else None,
        "commission_rate": commission_rate,
    }


async def update_landlord(
    session: AsyncSession,
    current_user: Users,
    landlord_id: str,
    updates: Dict,
    action: str = "updated",
) -> Tuple[Optional[str], Optional[str], Optional[Landlords]]:

    landlord_uuid, error = parse_uuid(landlord_id, "Invalid landlord ID")
    if error:
        return None, error, None

    landlord = (
        await session.execute(
            select(Landlords).where(Landlords.id == landlord_uuid)
        )
    ).scalar_one_or_none()

    if not landlord:
        return None, f"Landlord `{landlord_id}` not found", None

    try:
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

        return f"Landlord `{landlord.name}` {action} successfully", None, landlord

    except Exception as exc:
        logger.error(exc)
        await session.rollback()
        return None, str(exc), None


async def get_landlords_data(
    session: AsyncSession,
    show_deleted: bool = False,
):
    filters = []
    if not show_deleted:
        filters.append(Landlords.status != "deleted")

    stmt = (
        select(
            Landlords,
            func.count(Apartments.id).label("apartments")
        )
        .join(
            Apartments,
            and_(
                Apartments.landlord_id == Landlords.id,
                Apartments.status != "deleted",
            ),
            isouter=True,
        )
        .where(*filters)
        .group_by(Landlords.id)
        .order_by(Landlords.name)
    )

    rows = (await session.execute(stmt)).all()

    landlords = [
        {
            "id": l.id,
            "name": l.name,
            "email": l.email,
            "phone": l.phone,
            "id_number": l.id_number,
            "status": l.status,
            "apartments": count or 0,
        }
        for l, count in rows
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

    return landlords, stats


# ------------------------------------------------------------------
# Renderers
# ------------------------------------------------------------------

async def render_landlords(
    request: Request,
    session: AsyncSession,
    show_deleted: bool = False,
    success: Optional[str] = None,
    errors: Optional[str] = None,
):
    landlords, stats = await get_landlords_data(session, show_deleted)

    return templates.TemplateResponse(
        "landlords.html",
        {
            "request": request,
            "active": "landlords",
            "landlords": landlords,
            "stats": stats,
            "success": success,
            "errors": errors,
            "show_deleted": show_deleted,
        },
    )


async def render_new_landlord(
    request: Request,
    success: Optional[str] = None,
    errors: Optional[Dict] = None,
    form_data: Optional[Dict] = None,
):
    return templates.TemplateResponse(
        "landlords-new.html",
        {
            "request": request,
            "active": "new_landlord",
            "success": success,
            "errors": errors or {},
            "form_data": form_data or {},
        },
    )


async def render_edit_landlord(
    request: Request,
    session: AsyncSession,
    landlord_id: uuid.UUID,
    success: Optional[str] = None,
    errors: Optional[Dict] = None,
):
    landlord = (
        await session.execute(
            select(Landlords).where(Landlords.id == landlord_id)
        )
    ).scalar_one_or_none()

    if not landlord:
        errors = "Landlord not found"

    return templates.TemplateResponse(
        "landlords-edit.html",
        {
            "request": request,
            "active": "landlords",
            "landlord": landlord,
            "success": success,
            "errors": errors,
        },
    )


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.get("/landlords", response_class=HTMLResponse)
async def fetch(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
    show_deleted: bool = Query(False),
    toggle_status_id: Optional[str] = Query(None),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    success = errors = None

    if toggle_status_id:
        success, errors, _ = await update_landlord(
            session,
            current_user,
            toggle_status_id,
            {"toggle_status": True},
        )

    return await render_landlords(request, session, show_deleted, success, errors)


@router.post("/landlords", response_class=HTMLResponse)
async def post(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
    delete_id: Optional[str] = Form(None),
    restore_id: Optional[str] = Form(None),
    show_deleted: bool = Query(False),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    success = errors = None

    if delete_id or restore_id:
        success, errors, _ = await update_landlord(
            session,
            current_user,
            delete_id if delete_id else restore_id,
            {"status": "deleted" if delete_id else "active"},
            "deleted" if delete_id else "restored",
        )

    return await render_landlords(request, session, show_deleted, success, errors)


@router.get("/landlords/new", response_class=HTMLResponse)
async def new_landlord_form(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    return await render_new_landlord(request)


@router.post("/landlords/new", response_class=HTMLResponse)
async def create_landlord(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
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
    
    success = errors = ''

    errors = validate_landlord_form(name, email, phone, id_number, commission_rate)
    if errors:
        return await render_new_landlord(request, errors=errors, form_data=locals())

    now = datetime.utcnow()

    data = normalize_landlord_data(locals())
    landlord = Landlords(
        **data,
        created_at=now,
        created_by=current_user.id,
    )

    trial = (
        await session.execute(
            select(Packages).where(Packages.name == "TRIAL")
        )
    ).scalar_one()

    license = Licenses(
        key=str(uuid.uuid4()).upper(),
        package_id=trial.id,
        landlord_id=landlord.id,
        expires_at=now + timedelta(days=trial.validity),
        created_at=now,
        created_by=current_user.id,
    )

    try:
        session.add_all([landlord, license])
        await session.commit()
        success = f"Landlord `{landlord.name}` created successfully"

    except Exception as exc:
        logger.error(exc)
        await session.rollback()
        errors = str(exc)
        
    return await render_new_landlord(
        request,
        success=success,
        errors=errors,
        form_data=locals(),
    )


@router.get("/landlords/edit/{id}", response_class=HTMLResponse)
async def edit_landlord_form(
    request: Request,    
    id: str,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session)
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    
    landlord_id, errors = parse_uuid(id, "Invalid landlord ID")

    return await render_edit_landlord(
        request, 
        session,
        landlord_id,
        errors=errors
    )


@router.post("/landlords/edit/{id}", response_class=HTMLResponse)
async def edit_landlord(
    request: Request,
    id: str,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
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
        landlord_id, _ = parse_uuid(id, "")
        return await render_edit_landlord(request, session, landlord_id, errors=errors)

    success, errors, _ = await update_landlord(
        session,
        current_user,
        id,
        normalize_landlord_data(
            name, email, phone, id_number,
            kra_pin, address, bank_name, bank_account, commission_rate
        ),
    )

    landlord_id, _ = parse_uuid(id, "")
    return await render_edit_landlord(
        request, 
        session, 
        landlord_id, 
        success=success, 
        errors=errors
    )
