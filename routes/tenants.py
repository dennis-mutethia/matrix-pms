import logging, uuid
from datetime import datetime
from typing import Annotated, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.templating import PHONE_REGEX, READ_ONLY_FIELDS, templates
from utils.database import get_session
from utils.helpers import get_apartments, get_house_units, get_landlords, require_user
from utils.models import Apartments, House_Units, Landlords, Tenants, Users

logger = logging.getLogger(__name__)

router = APIRouter()

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
READ_ONLY_FIELDS = {"id", "created_at", "created_by"}


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


def validate_tenant_form(
    name: str,
    phone: str,
    id_number: str,
    email: str,
    next_of_kin_phone: Optional[str]
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
        
    if next_of_kin_phone and not PHONE_REGEX.match(next_of_kin_phone):
        errors["next_of_kin_phone"] = "Invalid next of kin phone number format"

    return errors


def normalize_tenant_data(
    name: str,
    phone: str,
    id_number: str,
    email: str,
    next_of_kin: Optional[str],
    next_of_kin_phone: Optional[str],
    occupation: Optional[str],
    employer: Optional[str]
) -> Dict:
    return {
        "name": name.strip().upper(),
        "email": email.strip().lower(),
        "phone": "254" + phone.strip()[-9:],
        "id_number": id_number.strip(),        
        "next_of_kin": next_of_kin.strip().upper() if next_of_kin else None,
        "next_of_kin_phone": "254" + next_of_kin_phone.strip()[-9:] if next_of_kin_phone else None,
        "occupation": occupation.strip().upper() if occupation else None,
        "employer": employer.strip().upper() if employer else None,
    }
    
async def update_tenant(
    session: AsyncSession,
    current_user: Users,
    tenant_id: str,
    updates: Dict,
    action: str = "updated",
) -> Tuple[Optional[str], Optional[str], Optional[Tenants]]:

    tenant_id_uuid, error = parse_uuid(tenant_id, "Invalid tenant ID")
    if error:
        return None, error, None

    tenant = (
        await session.execute(
            select(Tenants).where(Tenants.id == tenant_id_uuid)
        )
    ).scalar_one_or_none()

    if not tenant:
        return None, f"Tenant `{tenant_id}` not found", None

    try:
        for field, value in updates.items():
            if field not in READ_ONLY_FIELDS:
                setattr(tenant, field, value)

        tenant.updated_at = datetime.utcnow()
        tenant.updated_by = current_user.id

        await session.commit()
        await session.refresh(tenant)

        return f"Tenant `{tenant.name}` {action} successfully", None, tenant

    except Exception as exc:
        logger.error(exc)
        await session.rollback()
        return None, str(exc), None


# ─────────────────────────────────────────────
# Data Fetching
# ─────────────────────────────────────────────
async def get_tenants_data(
    session: AsyncSession,
    status: Optional[str],
    apartment_id: Optional[uuid.UUID],
    landlord_id: Optional[uuid.UUID],
    show_deleted: bool = False,
):
    filters = []

    if status:
        filters.append(Tenants.status == status)

    if not show_deleted:
        filters.extend([
            Tenants.status != "deleted",
            or_(House_Units.status != "deleted", House_Units.id.is_(None)),
            or_(Apartments.status != "deleted", Apartments.id.is_(None)),
            or_(Landlords.status != "deleted", Landlords.id.is_(None)),
        ])

    if apartment_id:
        filters.append(Apartments.id == apartment_id)

    if landlord_id:
        filters.append(Landlords.id == landlord_id)
    
    stmt = (
        select(
            Tenants,
            House_Units.name.label("house_unit"),
            Apartments.name.label("apartment"),
            Landlords.name.label("landlord")
        )
        .join(House_Units, Tenants.house_unit_id == House_Units.id, isouter=True)
        .join(Apartments, House_Units.apartment_id == Apartments.id, isouter=True)
        .join(Landlords, Apartments.landlord_id == Landlords.id, isouter=True)
        .where(*filters)
        .order_by(Tenants.name)
    )
    
    rows = (await session.execute(stmt)).all()

    tenants = [
        {
            "id": tenant.id,
            "name": tenant.name,
            "phone": tenant.phone,
            "id_number": tenant.id_number,
            "email": tenant.email,
            "status": tenant.status,
            "apartment": apartment,
            "landlord": landlord,
            "house_unit": house_unit,
        }
        for tenant, house_unit, apartment, landlord in rows
    ]

    return (
        tenants,
        await get_apartments(session),
        await get_landlords(session),
    )



# ─────────────────────────────────────────────
# Renderers
# ─────────────────────────────────────────────
async def render_tenants(
    request: Request,
    session: AsyncSession,
    status: Optional[str],
    apartment_id: Optional[uuid.UUID],
    landlord_id: Optional[uuid.UUID],
    show_deleted: bool = Query(False),
    success: Optional[str] = None,
    errors: Optional[str] = None,
):
    tenants, apartments, landlords = await get_tenants_data(
        session, status, apartment_id, landlord_id, show_deleted
    )

    return templates.TemplateResponse(
        "tenants.html",
        {
            "request": request,
            "active": "tenants",
            "tenants": tenants,
            "apartments": apartments,
            "landlords": landlords,
            "apartment_id": apartment_id,
            "landlord_id": landlord_id,
            "status": status,
            "success": success,
            "errors": errors,
        },
    )
    


async def render_new_tenant(
    request: Request,
    success: Optional[str] = None,
    errors: Optional[Dict] = None,
    form_data: Optional[Dict] = None,
):
    return templates.TemplateResponse(
        "tenants-new.html",
        {
            "request": request,
            "active": "new_tenant",
            "success": success,
            "errors": errors or {},
            "form_data": form_data or {},
        },
    )


async def render_edit_tenant(
    request: Request,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    success: Optional[str] = None,
    errors: Optional[Dict] = None,
):
    tenant = (
        await session.execute(
            select(Tenants).where(Tenants.id == tenant_id)
        )
    ).scalar_one_or_none()

    if not tenant:
        errors = "Tenant not found"

    return templates.TemplateResponse(
        "tenants-edit.html",
        {
            "request": request,
            "active": "tenants",
            "tenant": tenant,
            "success": success,
            "errors": errors,
        },
    )


async def render_assign_tenant_house_unit(
    request: Request,
    session: AsyncSession,
    tenant_id: uuid.UUID, 
    landlord_id: Optional[uuid.UUID] = None,  
    apartment_id: Optional[uuid.UUID] = None,
    house_unit_id: Optional[uuid.UUID] = None,
    success: Optional[str] = None,
    errors: Optional[Dict] = None,
):
    tenant = (
        await session.execute(
            select(Tenants).where(Tenants.id == tenant_id)
        )
    ).scalar_one_or_none()
    
    if not tenant:
        errors = "Tenant not found"
    
    house_units = await get_house_units(session, apartment_id)
    house_unit = next((a for a in house_units if a.id == house_unit_id), None)  
    
    apartment_id = house_unit.apartment_id if house_unit else apartment_id
    apartments = await get_apartments(session, landlord_id)
    apartment = next((a for a in apartments if a.id == apartment_id), None) 
    
    landlord_id = apartment.landlord_id if apartment else landlord_id
    landlords = await get_landlords(session)    
    landlord = next((a for a in landlords if a.id == landlord_id), None)

    return templates.TemplateResponse(
        "tenants-assign-house-unit.html",
        {
            "request": request,
            "active": "tenants",
            "tenant": tenant,
            "landlords": landlords,
            "apartments": apartments,
            "house_units": house_units,
            "landlord": landlord,
            "apartment": apartment,
            "house_unit": house_unit,
            "success": success,
            "errors": errors,
        },
    )

# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────
@router.get("/tenants", response_class=HTMLResponse)
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

    return await render_tenants(
        request,
        session,
        status,
        apartment_uuid,
        landlord_uuid,
        show_deleted,
        errors=err1 or err2,
    )


@router.post("/tenants", response_class=HTMLResponse)
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
        success, errors, _ = await update_tenant(
            session,
            current_user,
            delete_id if delete_id else restore_id,
            { "status": "deleted" if delete_id else "unassigned" },
            "deleted" if delete_id else "restored",
        )
        
    return await render_tenants(
        request,
        session,
        status,
        apartment_uuid,
        landlord_uuid,
        show_deleted,
        success,
        errors,
    )


@router.get("/tenants/new", response_class=HTMLResponse)
async def new_tenant_form(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)]
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    return await render_new_tenant(request)


@router.post("/tenants/new", response_class=HTMLResponse)
async def create_tenant(
    request: Request,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
    name: str = Form(...),    
    phone: str = Form(...),
    id_number: str = Form(...),
    email: str = Form(...),
    next_of_kin: Optional[str] = Form(None),
    next_of_kin_phone: Optional[str] = Form(None),
    occupation: Optional[str] = Form(None),
    employer: Optional[str] = Form(None),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    success = errors = ''
    
    errors = validate_tenant_form(name, phone, id_number, email, next_of_kin_phone)
    if errors:
        return await render_new_tenant(
            request, 
            errors=errors, 
            form_data=locals()
        )
        
    tenant = Tenants(
        **normalize_tenant_data(
            name, phone, id_number, email,
            next_of_kin, next_of_kin_phone, occupation, employer
        ),
        created_at=datetime.utcnow(),
        created_by=current_user.id,
    )
    
    try:
        session.add(tenant)
        await session.commit()
        success = f"Tenant `{tenant.name}` created successfully",

    except Exception as exc:
        logger.error(exc)
        await session.rollback()
        errors = str(exc)
        
    return await render_new_tenant(
        request,
        success=success,
        errors=errors,
        form_data=locals(),
    )
    

@router.get("/tenants/edit/{id}", response_class=HTMLResponse)
async def edit_tenant_form(
    request: Request,
    id: str,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    
    tenant_id, errors = parse_uuid(id, "Invalid tenant ID")

    return await render_edit_tenant(
        request, 
        session, 
        tenant_id, 
        errors=errors
    )
    

@router.post("/tenants/edit/{id}", response_class=HTMLResponse)
async def edit_tenant(
    request: Request,
    id: str,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
    name: str = Form(...),    
    phone: str = Form(...),
    id_number: str = Form(...),
    email: str = Form(...),
    next_of_kin: Optional[str] = Form(None),
    next_of_kin_phone: Optional[str] = Form(None),
    occupation: Optional[str] = Form(None),
    employer: Optional[str] = Form(None),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    errors = validate_tenant_form(name, phone, id_number, email, next_of_kin_phone)
    if errors:
        return await render_new_tenant(
            request, 
            errors=errors, 
            form_data=locals()
        )
        
    success, errors, _ = await update_tenant(
        session,
        current_user,
        id,
        normalize_tenant_data(
            name, phone, id_number, email,
            next_of_kin, next_of_kin_phone, occupation, employer
        )
    )

    tenant_id, _ = parse_uuid(id, "")
    return await render_edit_tenant(
        request, 
        session, 
        tenant_id, 
        success=success, 
        errors=errors
    )


@router.get("/tenants/assign-house-unit/{id}", response_class=HTMLResponse)
async def assign_tenant_house_unit_form(
    request: Request,
    id: str,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),      
    landlord_id: Optional[str] = Query(None),
    apartment_id: Optional[str] = Query(None),
    house_unit_id: Optional[str] = Query(None),
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    
    tenant_id, errors = parse_uuid(id, "Invalid tenant ID")
    landlord_id, errors = parse_uuid(landlord_id, "Invalid tenant ID")
    apartment_id, errors = parse_uuid(apartment_id, "Invalid tenant ID")
    house_unit_id, errors = parse_uuid(house_unit_id, "Invalid tenant ID")

    return await render_assign_tenant_house_unit(
        request, 
        session, 
        tenant_id, 
        landlord_id,
        apartment_id,
        house_unit_id,
        errors=errors
    )
    

@router.post("/tenants/assign-house-unit/{id}", response_class=HTMLResponse)
async def assign_tenant_house_unit(
    request: Request,
    id: str,
    current_user: Annotated[Users | RedirectResponse, Depends(require_user)],
    session: AsyncSession = Depends(get_session),
    house_unit_id: str = Form(...),  
):
    if isinstance(current_user, RedirectResponse):
        return current_user
    
    house_unit_id, errors = parse_uuid(house_unit_id, "")
    
    success, errors, _ = await update_tenant(
            session,
            current_user,
            id,
            { 
             "status": "occupied",
             "house_unit_id": house_unit_id
            },
            "assigned house"
        )
            
    return await render_assign_tenant_house_unit(
        request, 
        session, 
        tenant_id=id, 
        house_unit_id=house_unit_id,
        success=success,
        errors=errors
    )

