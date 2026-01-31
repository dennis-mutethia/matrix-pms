
import re
from datetime import datetime
from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from functools import wraps

from utils.helpers import get_current_user

READ_ONLY_FIELDS = {"id", "created_at", "created_by"}
PHONE_REGEX = re.compile(r"^\+?254[17]\d{8}$|^0[17]\d{8}$")

templates = Jinja2Templates(directory="templates")

templates.env.globals["now"] = datetime.now

def login_required(func):
    @wraps(func)
    async def wrapper(request: Request, **kwargs):
        user_or_redirect = await get_current_user(request)
        if isinstance(user_or_redirect, RedirectResponse):
            return user_or_redirect

        # Attach to request.state instead of passing as arg
        request.state.current_user = user_or_redirect

        return await func(request, **kwargs)
    return wrapper