from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from routes import apartments, dashboard, landlords, login, tenants
from utils.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(
    title="Matrix PMS", 
    lifespan=lifespan
)

# Mount static files (CSS, JS, images...)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include all routers
app.include_router(apartments.router)
app.include_router(dashboard.router) 
app.include_router(landlords.router) 
app.include_router(login.router)
app.include_router(tenants.router)


@app.get("/")
async def root():
    return RedirectResponse("/dashboard")