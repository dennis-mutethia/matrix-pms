
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# Tell Jinja2 where your templates live
templates = Jinja2Templates(directory="templates")

router = APIRouter(prefix="/tenants", tags=["Tenants"])

@router.get("/", response_class=HTMLResponse)
async def get_tenants(request: Request):
    return templates.TemplateResponse(
        "index.html",          # ← template name
        {"request": request, "name": "Dennis", "items": [1, 2, 3, 4]}
    )