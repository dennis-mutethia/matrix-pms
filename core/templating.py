
from datetime import datetime
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

templates.env.globals["now"] = datetime.now

# Optional: add globals, filters, etc.
# templates.env.globals["app_name"] = "My Property Manager"