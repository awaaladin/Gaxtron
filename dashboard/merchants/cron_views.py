"""Vercel Cron target — ported from GaX/app/api/routers/cron.py. Runs the same reconciliation
the run_listener management command does, for serverless deployments with no persistent worker."""
import logging
import os

from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView

from .reconcile_service import get_reconciler

logger = logging.getLogger(__name__)


def _cron_secret() -> str:
    return (settings.CRON_SECRET or os.getenv("CRON_SECRET") or "").strip()


class CronCheckPaymentsView(APIView):
    """
    Vercel Cron target. Also callable manually:
      curl -H "Authorization: Bearer $CRON_SECRET" https://your-app.vercel.app/api/cron/check-payments
    """

    def get(self, request):
        secret = _cron_secret()
        if not secret:
            return Response({"detail": "CRON_SECRET not set. Add it in Vercel project Environment Variables."}, status=503)

        authorization = request.headers.get("Authorization")
        if authorization != f"Bearer {secret}":
            return Response({"detail": "Invalid cron authorization"}, status=401)

        payment_id = request.GET.get("payment_id")
        payment_id = int(payment_id) if payment_id else None

        logger.info("Cron check-payments started path=%s", request.path)
        try:
            result = get_reconciler().run_cron_cycle(payment_id=payment_id)
            logger.info("Cron check-payments done: %s", result)
            return Response({"ok": True, **result})
        except Exception as e:
            logger.exception("Cron check-payments failed")
            return Response({"detail": str(e)}, status=500)
