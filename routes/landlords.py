
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select
from core.templating import templates
from collections import Counter

from utils.models import Apartments, Landlords
from utils.database import get_session

router = APIRouter()

@router.get("/landlords", response_class=HTMLResponse)
async def get_tenants(
    request: Request,
    session: AsyncSession = Depends(get_session),
    #current_user: Users = Depends(get_current_user)
):
    
    stmt = (
        select(
            Landlords,
            func.count(Apartments.id).label("apartment_count")
        )
        .join(Apartments, Apartments.landlord_id == Landlords.id, isouter=True)
        .group_by(Landlords.id)           # ← very important!
        .order_by(Landlords.id)           # optional but nice
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
    
    print(stats)

    return templates.TemplateResponse(
        "landlords.html",
        {
            "request": request,
            "active": "landlords",
            "landlords": landlords,  
            "stats": stats   
        }
    )