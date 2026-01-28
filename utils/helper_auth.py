
import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi.responses import RedirectResponse
import jwt
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from utils.database import get_session
from utils.models import Users


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


async def get_current_user_or_redirect(
    request: Request,
    session: AsyncSession = Depends(get_session)
) -> Users:
    """
    Dependency: returns current user or redirects to login
    """
    token = request.cookies.get("access_token")

    if not token:
        return RedirectResponse(
            url="/login?next=" + str(request.url),
            status_code=status.HTTP_303_SEE_OTHER
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub") or 0)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError):
        return RedirectResponse(
            url="/login?next=" + str(request.url),
            status_code=status.HTTP_303_SEE_OTHER
        )

    stmt = select(Users).where(Users.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        return RedirectResponse(
            url="/login?next=" + str(request.url),
            status_code=status.HTTP_303_SEE_OTHER
        )

    return user