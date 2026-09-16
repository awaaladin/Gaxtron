"""
Payment REST views — the Django replacement for GaX/app/api/routers/{payments,checkout}.py.
Payment-mutating endpoints use ApiKeyAuthentication only (matches GaX/app/api/deps.py's split
exactly — a JWT does not work here, same as before).
"""
import logging

from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from . import alchemy_webhook_service
from .authentication import ApiKeyAuthentication
from .models import Payment
from .payment_service import PaymentService
from .reconcile_service import get_reconciler
from .serializers import (
    CreatePaymentRequestSerializer,
    CreatePaymentResponseSerializer,
    PaymentResponseSerializer,
    PublicPaymentStatusSerializer,
    VerifyPaymentResponseSerializer,
)

logger = logging.getLogger(__name__)


class CreatePaymentView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    def post(self, request):
        data = CreatePaymentRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        try:
            payment = PaymentService.create_payment(
                user_id=request.user.id,
                amount=v["amount"],
                callback_url=str(v["callback_url"]),
                idempotency_key=v.get("idempotency_key"),
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("create_payment failed for user %s", request.user.id)
            return Response({"detail": "Failed to create payment"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if alchemy_webhook_service.is_configured():
            try:
                alchemy_webhook_service.register_address(payment.wallet_address)
            except Exception:
                logger.exception("Alchemy address registration failed for payment %s", payment.id)

        try:
            get_reconciler().run_batch(payment_id=payment.id)
        except Exception:
            logger.exception("Background reconcile failed for payment %s", payment.id)

        return Response(CreatePaymentResponseSerializer(payment).data, status=status.HTTP_201_CREATED)


class ListPaymentsView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    def get(self, request):
        payments = Payment.objects.filter(user=request.user).order_by("-created_at")[:50]
        return Response(PaymentResponseSerializer(payments, many=True).data)


class PaymentMerchantDetailView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    def get(self, request, payment_id: int):
        payment = PaymentService.get_payment(payment_id, request.user.id)
        if not payment:
            raise NotFound("Payment not found")
        return Response(PaymentResponseSerializer(payment).data)


class VerifyPaymentView(APIView):
    authentication_classes = [ApiKeyAuthentication]

    def get(self, request, payment_id: int):
        payment = PaymentService.get_payment(payment_id, request.user.id)
        if not payment:
            raise NotFound("Payment not found")
        if payment.status == "pending":
            try:
                get_reconciler().run_batch(payment_id=payment.id)
                payment.refresh_from_db()
            except Exception:
                logger.exception("Reconcile on verify failed for payment %s", payment_id)
        return Response(VerifyPaymentResponseSerializer(payment).data)


class PublicPaymentStatusView(APIView):
    """No auth — powers checkout-page.js's status polling."""

    def get(self, request, payment_ref: str):
        from django.conf import settings

        payment = PaymentService.get_payment_by_ref(payment_ref)
        if not payment:
            raise NotFound("Payment not found")
        if settings.CHECKOUT_RECONCILE_ON_POLL and payment.status == "pending":
            try:
                get_reconciler().run_batch(payment_id=payment.id)
                payment.refresh_from_db()
            except Exception:
                pass
        return Response(PublicPaymentStatusSerializer(payment).data)


def _canonical_pay_path(payment_ref: str) -> str:
    return f"/pay/{payment_ref}/"


def checkout_redirect(request, payment_ref: str):
    return HttpResponseRedirect(_canonical_pay_path(payment_ref))


def payment_link_redirect(request, payment_ref: str):
    return HttpResponseRedirect(_canonical_pay_path(payment_ref))


def pay_query_redirect(request):
    from django.http import HttpResponseBadRequest

    payment_ref = request.GET.get("ref") or request.GET.get("token") or request.GET.get("payment")
    if not payment_ref:
        return HttpResponseBadRequest("Missing payment reference (?ref=pay_...)")
    return HttpResponseRedirect(_canonical_pay_path(payment_ref))
