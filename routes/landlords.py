
import re, uuid
from collections import Counter
from datetime import datetime, timedelta
from typing import Annotated, Dict, Optional
from fastapi import APIRouter, Depends, Form, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import delete, func, select

from core.templating import templates
from utils.helper_auth import get_current_user_or_redirect
from utils.models import Apartments, Landlords, Licenses, Packages, Users
from utils.database import get_session

router = APIRouter()

async def update_landlord(
    session: AsyncSession,
    current_user: Users,
    id: str,
    columns_key_value: Dict
):
    try:
        statement = select(Landlords).where(Landlords.id == uuid.UUID(id))
        result = await session.execute(statement)
        db_landlord = result.scalar_one_or_none()

        if not db_landlord:
            return None, f"Landlord with ID `{id}` not found", None
        
        if columns_key_value.get("toggle_status"):
            db_landlord.status = (
                "inactive" if db_landlord.status == "active" else "active"
            )      
        else:
            readonly_fields = {
                "id",
                "created_at",
                "created_by"
            }  
            
            for column, value in columns_key_value.items():
                if column not in readonly_fields:
                    setattr(db_landlord, column, value)

        # audit fields
        db_landlord.updated_by = current_user.id
        db_landlord.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(db_landlord)

        return f"Landlord: `{db_landlord.name}` updated successfully", None, db_landlord

    except Exception as e:
        await session.rollback()
        return None, str(e)

    except Exception as exc:
        await session.rollback()
        return None, str(exc)

    
@router.get("/landlords", response_class=HTMLResponse)
async def get(
    request: Request,
    current_user_or_redirect: Annotated[Users | RedirectResponse, Depends(get_current_user_or_redirect)],
    session: AsyncSession = Depends(get_session),
    toggle_status_id: Annotated[str | None, Query()] = None,
    delete_id: Annotated[str | None, Query()] = None,
):
    if isinstance(current_user_or_redirect, RedirectResponse):
        return current_user_or_redirect

    current_user: Users = current_user_or_redirect
    
    success = None 
    errors = None
    if toggle_status_id:
        success, errors, landlord = await update_landlord(
            session,
            current_user,
            id=toggle_status_id,
            columns_key_value={
                "toggle_status" : True
            }
        )
        
    if delete_id:
        success, errors, landlord = await update_landlord(
            session,
            current_user,
            id=delete_id,
            columns_key_value={
                "status" : "deleted"
            }
        )
    
    stmt = (
        select(
            Landlords,
            func.count(Apartments.id).label("apartment_count")
        )
        .join(Apartments, Apartments.landlord_id == Landlords.id, isouter=True)
        .where(Landlords.status != "deleted")
        .group_by(Landlords.id)           # ← very important!
        .order_by(Landlords.name, Landlords.email, Landlords.phone)           # optional but nice
    )

    result = await session.execute(stmt)
    rows = result.all()   # list of (Landlord, int) tuples

    # Option 1: Cleanest – create simple dicts (recommended for templates)
    landlords = [
        {
            "id": landlord.id,
            "name": landlord.name,           # assuming these fields exist
            "email": landlord.email,
            "phone": landlord.phone,
            "id_number": landlord.id_number,
            "status": landlord.status,
            "apartments": count or 0,
        }
        for landlord, count in rows
    ]

    status_counts = Counter(d["status"] for d in landlords)
    apt_counts = Counter("with" if d["apartments"] > 0 else "without" for d in landlords)

    stats = {
        "total_landlords": len(landlords),
        "active_landlords": status_counts.get("active", 0),
        "inactive_landlords": status_counts.get("inactive", 0),  
        "with_properties": apt_counts["with"],
        "without_properties": apt_counts["without"]
    }

    return templates.TemplateResponse(
        "landlords.html",
        {
            "request": request,
            "active": "landlords",
            "landlords": landlords,  
            "stats": stats,
            "success": success,
            "errors": errors   
        }
    )
        
@router.get("/new-landlord", response_class=HTMLResponse)
async def get_new(
    request: Request,
    current_user_or_redirect: Annotated[Users | RedirectResponse, Depends(get_current_user_or_redirect)],
    session: AsyncSession = Depends(get_session)
):
    if isinstance(current_user_or_redirect, RedirectResponse):
        return current_user_or_redirect

    current_user: Users = current_user_or_redirect
    
    return templates.TemplateResponse(
        "landlords-new.html",
        {
            "request": request,
            "active": "new_landlord"
        }
    )

@router.post("/new-landlord", response_class=HTMLResponse)
async def post_new_landlord(
    request: Request,
    current_user_or_redirect: Annotated[Users | RedirectResponse, Depends(get_current_user_or_redirect)],
    session: AsyncSession = Depends(get_session),

    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    id_number: str = Form(...),
    kra_pin: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    bank_name: Optional[str] = Form(None),
    bank_account: Optional[str] = Form(None),
    commission_rate: Optional[float] = Form(None)
):
    if isinstance(current_user_or_redirect, RedirectResponse):
        return current_user_or_redirect

    current_user: Users = current_user_or_redirect
    
    errors = {}

    if not name.strip():
        errors["name"] = "Name is required"

    if "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Please enter a valid email address"

    if not id_number.strip():
        errors["id_number"] = "ID Number is required"

    # Optional: phone number format check (example for Kenyan numbers)
    if phone and not re.match(r"^\+?254[17]\d{8}$|^0[17]\d{8}$", phone):
        errors["phone"] = "Invalid phone number format"

    if commission_rate is not None and (commission_rate < 0 or commission_rate > 100):
        errors["commission_rate"] = "Commission rate must be between 0 and 100"
        
    # If there are validation errors → re-render form with values & errors
    if errors:
        form_data = {
            "name": name,
            "email": email,
            "phone": phone,
            "id_number": id_number,
            "kra_pin": kra_pin,
            "address": address,
            "bank_name": bank_name,
            "bank_account": bank_account,
            "commission_rate": commission_rate
        }
        return templates.TemplateResponse(
            "landlords-new.html",
            {
                "request": request,
                "active": "new_landlord",
                "form_data": form_data,
                "errors": errors,
                "success": None,
            }
        )

    # ────────────────────────────────────────────────
    # Create new landlord
    now = datetime.utcnow()

    new_landlord = Landlords(
        name=name.strip().upper(),
        email=email.strip().lower(),
        phone=phone.strip(),
        id_number=id_number.strip(),
        kra_pin=kra_pin.strip().upper() if kra_pin else None,
        address=address.strip().upper() if address else None,
        bank_name=bank_name.strip().upper() if bank_name else None,
        bank_account=bank_account.strip().upper() if bank_account else None,
        commission_rate=commission_rate,
        created_at=now,
        created_by=current_user.id
    ) 
    
    statement = (
        select(Packages)
        .where(Packages.name == "TRIAL")
    )

    result = await session.execute(statement)
    trial_package = result.scalar_one_or_none() 
    
    new_license = Licenses(
        key=str(uuid.uuid4()).upper(),
        package_id=trial_package.id,
        landlord_id=new_landlord.id,
        expires_at=now + timedelta(days=trial_package.validity),
        created_at=now,
        created_by=current_user.id
    )

    try:  
        session.add(new_landlord)
        session.add(new_license)
        await session.commit()
        await session.refresh(new_landlord)
        
        return templates.TemplateResponse(
            "landlords-new.html",
            {
                "request": request,
                "active": "new_landlord",
                "success": f"Landlord {new_landlord.name} created successfully (ID: {new_landlord.id})",
                "form_data": {},  # clear form
                "errors": {},
            }
        )

    except Exception as exc:
        await session.rollback()
        return templates.TemplateResponse(
            "landlords-new.html",
            {
                "request": request,
                "active": "new_landlord",
                "errors": {"general": str(exc)},
                "form_data": request._form._dict,  # best effort
                "success": None,
            }
        )
        

    
@router.get("/edit-landlord", response_class=HTMLResponse)
async def get_edit(
    request: Request,
    current_user_or_redirect: Annotated[Users | RedirectResponse, Depends(get_current_user_or_redirect)],
    session: AsyncSession = Depends(get_session),    
    id: Annotated[str | None, Query()] = None,
):
    if isinstance(current_user_or_redirect, RedirectResponse):
        return current_user_or_redirect
    
    if not id or not uuid.UUID(id):
        return templates.TemplateResponse(
            "landlords-edit.html",
            {
                "request": request,
                "active": "landlords",
                "errors": "Invalid Landlord ID"
            }
        )
        
    statement = select(Landlords).where(Landlords.id == uuid.UUID(id))
    result = await session.execute(statement)
    db_landlord = result.scalar_one_or_none()

    if not db_landlord:
        return templates.TemplateResponse(
            "landlords-edit.html",
            {
                "request": request,
                "active": "landlords",
                "errors": f"Landlord with ID `{id}` not found"
            }
        )
    
    return templates.TemplateResponse(
        "landlords-edit.html",
        {
            "request": request,
            "active": "landlords",
            "landlord": db_landlord
        }
    )

@router.post("/edit-landlord", response_class=HTMLResponse)
async def post_edit(
    request: Request,
    current_user_or_redirect: Annotated[Users | RedirectResponse, Depends(get_current_user_or_redirect)],
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
    commission_rate: Optional[float] = Form(None)
):
    if isinstance(current_user_or_redirect, RedirectResponse):
        return current_user_or_redirect

    current_user: Users = current_user_or_redirect
    
    errors = {}

    if not name.strip():
        errors["name"] = "Name is required"

    if "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Please enter a valid email address"

    if not id_number.strip():
        errors["id_number"] = "ID Number is required"

    # Optional: phone number format check (example for Kenyan numbers)
    if phone and not re.match(r"^\+?254[17]\d{8}$|^0[17]\d{8}$", phone):
        errors["phone"] = "Invalid phone number format"

    if commission_rate is not None and (commission_rate < 0 or commission_rate > 100):
        errors["commission_rate"] = "Commission rate must be between 0 and 100"
        
    # If there are validation errors → re-render form with values & errors
    if errors:
        form_data = {
            "name": name,
            "email": email,
            "phone": phone,
            "id_number": id_number,
            "kra_pin": kra_pin,
            "address": address,
            "bank_name": bank_name,
            "bank_account": bank_account,
            "commission_rate": commission_rate
        }
        return templates.TemplateResponse(
            "landlords-new.html",
            {
                "request": request,
                "active": "new_landlord",
                "form_data": form_data,
                "errors": errors,
                "success": None,
            }
        )

    success, errors, landlord = await update_landlord(
        session,
        current_user,
        id=id,
        columns_key_value={
            "name": name,
            "email": email,
            "phone": phone,
            "id_number": id_number,
            "kra_pin": kra_pin,
            "address": address,
            "bank_name": bank_name,
            "bank_account": bank_account,
            "commission_rate": commission_rate
        }
    )    
    
    return templates.TemplateResponse(
        "landlords-edit.html",
        {
            "request": request,
            "active": "landlords",
            "success": success,
            "errors": errors,
            "landlord": landlord
        }
    )