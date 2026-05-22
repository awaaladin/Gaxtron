"""
Vercel Cron — blockchain reconciliation (replaces always-on worker on serverless).
"""
import logging
import os

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.config import settings
from app.services.reconcile_service import get_reconciler

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cron", tags=["cron"])


def _cron_secret() -> str:
    return (settings.cron_secret or os.getenv("CRON_SECRET") or "").strip()


def verify_cron_request(authorization: str | None = Header(None)) -> None:
    secret = _cron_secret()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="CRON_SECRET not set. Add it in Vercel project Environment Variables.",
        )
    expected = f"Bearer {secret}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid cron authorization")


@router.get("/check-payments")
def cron_check_payments(
    request: Request,
    authorization: str | None = Header(None),
    payment_id: int | None = Query(None, description="Optional: reconcile one payment"),
):
    """
    Vercel Cron target (minimum schedule: every 1 minute on Hobby).

    Also callable manually:
      curl -H "Authorization: Bearer $CRON_SECRET" https://your-app.vercel.app/api/cron/check-payments
    """
    verify_cron_request(authorization)
    logger.info("Cron check-payments started path=%s", request.url.path)
    try:
        result = get_reconciler().run_cron_cycle(payment_id=payment_id)
        logger.info("Cron check-payments done: %s", result)
        return {"ok": True, **result}
    except Exception as e:
        logger.exception("Cron check-payments failed")
        raise HTTPException(status_code=500, detail=str(e)) from e
