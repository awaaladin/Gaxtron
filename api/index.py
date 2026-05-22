"""
Vercel serverless entry — re-exports FastAPI app from GaX/.
Set Vercel Root Directory to repo root (Gaxtron).
"""
import sys
from pathlib import Path

_GAX = Path(__file__).resolve().parent.parent / "GaX"
if str(_GAX) not in sys.path:
    sys.path.insert(0, str(_GAX))

from app.main import app  # noqa: E402
