"""Ported from GaX/app/services/payment_service.py — Django ORM instead of SQLAlchemy."""
import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from .exceptions import DuplicatePaymentError
from .models import Payment
from .url_validation import CallbackUrlError, validate_callback_url
from .wallet_service import WalletService

logger = logging.getLogger(__name__)

ETH_CHAIN = "ETH"
ETH_CURRENCY = "ETH"


def build_payment_url(ref: str) -> str:
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/pay/{ref}"


class PaymentService:
    @staticmethod
    def generate_public_token() -> str:
        return f"pay_{uuid.uuid4().hex}"

    @staticmethod
    def build_payment_url(payment: Payment) -> str:
        ref = payment.public_token or str(payment.id)
        return build_payment_url(ref)

    @staticmethod
    def get_payment_by_ref(ref: str, user_id: int | None = None) -> Payment | None:
        if ref.startswith("pay_"):
            q = Payment.objects.filter(public_token=ref)
        elif ref.isdigit():
            q = Payment.objects.filter(id=int(ref))
        else:
            return None
        if user_id is not None:
            q = q.filter(user_id=user_id)
        return q.first()

    @staticmethod
    @db_transaction.atomic
    def create_payment(user_id: int, amount, callback_url: str, idempotency_key: str | None = None) -> Payment:
        try:
            validate_callback_url(str(callback_url))
        except CallbackUrlError as e:
            raise ValueError(str(e)) from e

        if idempotency_key:
            existing = (
                Payment.objects.select_for_update()
                .filter(idempotency_key=idempotency_key, user_id=user_id)
                .first()
            )
            if existing:
                logger.info("Idempotent payment hit: %s", existing.id)
                return existing

        wallet = WalletService.generate_wallet(ETH_CHAIN, ETH_CURRENCY, user_id=user_id)
        event_id = str(uuid.uuid4())
        public_token = PaymentService.generate_public_token()
        expires_at = timezone.now() + timedelta(minutes=settings.PAYMENT_EXPIRY_MINUTES)

        payment = Payment.objects.create(
            user_id=user_id,
            amount=amount,
            chain=ETH_CHAIN,
            currency=ETH_CURRENCY,
            status="pending",
            wallet_address=wallet.address,
            callback_url=str(callback_url),
            idempotency_key=idempotency_key,
            public_token=public_token,
            event_id=event_id,
            expires_at=expires_at,
            confirmations=0,
        )
        wallet.payment_id = payment.id
        wallet.save(update_fields=["payment_id"])

        logger.info(
            "ETH payment %s token=%s user=%s amount=%s url=%s",
            payment.id, public_token, user_id, payment.amount, PaymentService.build_payment_url(payment),
        )
        return payment

    @staticmethod
    def get_payment(payment_id: int, user_id: int | None = None) -> Payment | None:
        q = Payment.objects.filter(id=payment_id)
        if user_id is not None:
            q = q.filter(user_id=user_id)
        return q.first()

    @staticmethod
    def get_payment_for_update(payment_id: int) -> Payment | None:
        return Payment.objects.select_for_update().filter(id=payment_id).first()

    @staticmethod
    def expire_stale_payments() -> int:
        now = timezone.now()
        stale = Payment.objects.filter(status="pending", expires_at__isnull=False, expires_at__lt=now)
        count = stale.count()
        stale.update(status="failed")
        return count

    @staticmethod
    def confirm_payment(payment: Payment, tx_hash: str, from_address: str = "unknown", confirmations: int = 0) -> Payment:
        if payment.status == "confirmed":
            if payment.tx_hash == tx_hash:
                return payment
            raise DuplicatePaymentError()
        if payment.status != "pending":
            raise DuplicatePaymentError()

        payment.status = "confirmed"
        payment.tx_hash = tx_hash
        payment.confirmations = confirmations
        payment.confirmed_at = timezone.now()
        payment.save(update_fields=["status", "tx_hash", "confirmations", "confirmed_at"])
        logger.info("Payment %s confirmed tx=%s confirmations=%s", payment.id, tx_hash, confirmations)
        return payment

    @staticmethod
    def fail_payment(payment: Payment) -> Payment:
        if payment.status == "pending":
            payment.status = "failed"
            payment.save(update_fields=["status"])
        return payment

    @staticmethod
    def update_pending_confirmations(payment: Payment, tx_hash: str, confirmations: int) -> Payment:
        if payment.status == "pending" and tx_hash:
            payment.tx_hash = tx_hash
            payment.confirmations = confirmations
            payment.save(update_fields=["tx_hash", "confirmations"])
        return payment
