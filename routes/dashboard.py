
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from core.templating import templates

router = APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
async def get_tenants(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",          
        {
            "request": request, 
            "active": "dashboard"
        }
    )