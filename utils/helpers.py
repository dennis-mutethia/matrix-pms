
import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional
import uuid

from fastapi.responses import RedirectResponse
import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from utils.database import get_session
from utils.models import Apartments, House_Units, Landlords, Users


SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

def hash_password(password):
    password_bytes = password.encode('utf-8')
    hash_object = hashlib.sha256(password_bytes)
    return hash_object.hexdigest()
    
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def authenticate_user(phone: str, password: str, session: AsyncSession) -> Users | None:
    statement = select(Users).where(Users.phone == phone)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()
    if user and user.password == hash_password(password):
        return user
    return None


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Users:
    token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = (
        await session.execute(
            select(Users).where(Users.id == user_id)
        )
    ).scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    return user


async def require_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Users:
    try:
        return await get_current_user(request, session)
    except HTTPException:
        return RedirectResponse(
            url=f"/login?next={request.url.path}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
        

async def get_landlords(
    session: AsyncSession,
) -> list[dict]:
    stmt = (
        select(Landlords)
        .where(Landlords.status != "deleted")
        .order_by(Landlords.name)
    )
    
    return (await session.execute(stmt)).scalars().all()


async def get_apartments(
    session: AsyncSession,
    landlord_id: Optional[uuid.UUID] = None,
) -> list[dict]:
    
    filters = [Apartments.status != "deleted"]
    if landlord_id:
        filters.append(Apartments.landlord_id == landlord_id)
        
    stmt = (
        select(Apartments)
        .where(*filters)
        .order_by(Apartments.name)
    )
    
    return  (await session.execute(stmt)).scalars().all()


async def get_house_units(
    session: AsyncSession,
    apartment_id: Optional[uuid.UUID] = None,
) -> list[dict]:
    
    filters = [House_Units.status != "deleted"]
    if apartment_id:
        filters.append(House_Units.apartment_id == apartment_id)
        
    stmt = (
        select(House_Units)
        .where(*filters)
        .order_by(House_Units.name)
    )
    
    return (await session.execute(stmt)).scalars().all()