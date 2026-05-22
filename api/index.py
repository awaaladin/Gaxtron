"""
Vercel FastAPI entrypoint — exports `app` for tool.vercel.entrypoint in pyproject.toml.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_GAX = _ROOT / "GaX"
if str(_GAX) not in sys.path:
    sys.path.insert(0, str(_GAX))

from app.main import app  # noqa: E402

__all__ = ["app"]
