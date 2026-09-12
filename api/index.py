"""
Vercel WSGI entrypoint — exports `app` for tool.vercel.entrypoint in pyproject.toml.
Wraps the Django project in dashboard/ (the FastAPI/GaX backend has been retired).
"""
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DASHBOARD = _ROOT / "dashboard"
if str(_DASHBOARD) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.core.wsgi import get_wsgi_application  # noqa: E402

app = get_wsgi_application()

__all__ = ["app"]
