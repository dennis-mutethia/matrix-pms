
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from core.templating import templates

router = APIRouter()

@router.get("/apartments", response_class=HTMLResponse)
async def get_tenants(request: Request):
    return templates.TemplateResponse(
        "apartments.html",          
        {
            "request": request, 
            "active": "apartments"
        }
    )