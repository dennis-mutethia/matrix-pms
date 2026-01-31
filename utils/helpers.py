
import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi.responses import RedirectResponse
import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from utils.database import get_session
from utils.models import Apartments, Landlords, Users


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



async def get_landlords(session: AsyncSession) -> list[dict]:
    stmt = (
        select(Landlords)
        .where(Landlords.status != "deleted")
        .order_by(Landlords.name)
    )
    landlords = (await session.execute(stmt)).scalars().all()

    return [{"id": l.id, "name": l.name} for l in landlords]


async def get_apartments(session: AsyncSession) -> list[dict]:
    stmt = (
        select(Apartments)
        .where(Apartments.status != "deleted")
        .order_by(Apartments.name)
    )
    apartments = (await session.execute(stmt)).scalars().all()

    return [{"id": a.id, "name": a.name} for a in apartments]