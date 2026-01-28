from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from routes import tenants

app = FastAPI()

# Mount static files (CSS, JS, images...)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include all routers
app.include_router(tenants.router)