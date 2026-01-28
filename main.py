from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routes import apartments, dashboard, tenants

app = FastAPI()

# Mount static files (CSS, JS, images...)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include all routers
app.include_router(apartments.router)
app.include_router(tenants.router)
app.include_router(dashboard.router) 