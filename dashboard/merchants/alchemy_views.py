"""Receiver for Alchemy's Address Activity push webhook — see alchemy_webhook_service.py
and VERCEL.md section 7. Fully inert until ALCHEMY_WEBHOOK_SIGNING_KEY is set: without it,
verify_signature() always rejects, so this endpoint just 401s and nothing calls it anyway
since register_address() never runs unauthenticated Alchemy webhooks into existence.
"""
import json
import logging
from decimal import Decimal, InvalidOperation

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import alchemy_webhook_service
from .models import Payment
from .payment_service import PaymentService
from .reconcile_service import get_reconciler

logger = logging.getLogger(__name__)

# Alchemy's Address Activity "category" for a plain native ETH transfer. Excludes "token"
# (ERC-20) and NFT categories — this app only ever creates ETH-denominated payments (see
# ETH_CURRENCY in payment_service.py), so a token transfer to a deposit address is never
# a valid match here even though it reuses the same "value" field.
NATIVE_ETH_CATEGORIES = {"external", "internal"}


@method_decorator(csrf_exempt, name="dispatch")
class AlchemyAddressActivityView(APIView):
    """Verified via HMAC (X-Alchemy-Signature), not our usual API-key auth — the caller is
    Alchemy's webhook dispatcher, not a merchant."""
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        raw_body = request.body
        signature = request.headers.get("X-Alchemy-Signature")

        if not alchemy_webhook_service.verify_signature(raw_body, signature):
            return Response({"detail": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            payload = json.loads(raw_body)
        except ValueError:
            return Response({"detail": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST)

        activities = (payload.get("event") or {}).get("activity") or []
        for activity in activities:
            try:
                self._handle_activity(activity)
            except Exception:
                logger.exception("Failed to process Alchemy activity item")

        return Response({"status": "ok"})

    def _handle_activity(self, activity: dict) -> None:
        if activity.get("category") not in NATIVE_ETH_CATEGORIES:
            return

        to_address = activity.get("toAddress") or ""
        tx_hash = activity.get("hash")
        raw_value = activity.get("value")
        if not to_address or not tx_hash or raw_value is None:
            return

        try:
            value = Decimal(str(raw_value))
        except InvalidOperation:
            return

        payment = Payment.objects.filter(wallet_address__iexact=to_address, status="pending").first()
        if not payment or payment.tx_hash:
            return
        if value < payment.amount * Decimal("0.99"):
            return

        # Setting tx_hash here just short-circuits the block-scan half of detection — the
        # existing reconcile path (chains.EthereumService.get_confirmations, a cheap 2-call
        # lookup once tx_hash is known) takes it from here, same as if the poll loop had
        # found it itself. All finalize/webhook-delivery logic is untouched and reused as-is.
        PaymentService.update_pending_confirmations(payment, tx_hash, confirmations=0)
        try:
            get_reconciler().run_batch(payment_id=payment.id)
        except Exception:
            logger.exception("Reconcile after Alchemy activity failed for payment %s", payment.id)
