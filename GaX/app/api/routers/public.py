"""Public read-only endpoints (no mock metrics)."""
from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/config")
def public_config():
    """Network and security facts from server configuration — not fabricated stats."""
    return {
        "network": settings.blockchain_network,
        "currency": "ETH",
        "required_confirmations": settings.eth_required_confirmations,
        "webhook_signing": "HMAC-SHA256",
    }
