"""
Payment reconciliation — ported from GaX/app/services/reconcile_service.py +
GaX/app/workers/listener.py's _check_payment/_finalize_payment (merged into one place since
nothing else called the listener class directly). Used by checkout-page polling and the
run_listener management command.
"""
import logging

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from .chains import IncomingPaymentResult
from .exceptions import DuplicatePaymentError
from .models import Payment, Transaction
from .payment_processor import get_payment_processor
from .payment_service import PaymentService
from .queue import enqueue_webhook, is_event_processed, mark_event_processed
from .webhook_service import WebhookService

logger = logging.getLogger(__name__)


class PaymentReconciler:
    def __init__(self):
        self.processor = get_payment_processor()

    def _check_payment(self, payment: Payment) -> None:
        if payment.status != "pending":
            return
        if payment.expires_at and payment.expires_at < timezone.now():
            PaymentService.fail_payment(payment)
            return

        chain = payment.chain or "ETH"
        try:
            if payment.tx_hash:
                confirmations = self.processor.get_confirmations(chain, payment.tx_hash)
                PaymentService.update_pending_confirmations(payment, payment.tx_hash, confirmations)
                if confirmations >= settings.ETH_REQUIRED_CONFIRMATIONS:
                    result = IncomingPaymentResult(tx_hash=payment.tx_hash, from_address="unknown", confirmations=confirmations)
                    self._finalize_payment(payment, result, chain)
                return

            result = self.processor.detect_payment(chain, payment.wallet_address, payment.amount, payment.currency)
        except Exception:
            logger.exception("detect_payment failed payment=%s chain=%s", payment.id, chain)
            return

        if not result:
            return

        required = settings.ETH_REQUIRED_CONFIRMATIONS
        if result.confirmations < required:
            PaymentService.update_pending_confirmations(payment, result.tx_hash, result.confirmations)
            return

        self._finalize_payment(payment, result, chain)

    def _finalize_payment(self, payment: Payment, result, chain: str) -> None:
        event_id = f"{chain}_{result.tx_hash}"
        if is_event_processed(event_id):
            return
        if Transaction.objects.filter(tx_hash=result.tx_hash).exists():
            mark_event_processed(event_id)
            return

        try:
            with db_transaction.atomic():
                locked = PaymentService.get_payment_for_update(payment.id)
                if not locked or locked.status != "pending":
                    return
                Transaction.objects.create(
                    user_id=locked.user_id,
                    payment_id=locked.id,
                    tx_hash=result.tx_hash,
                    amount=locked.amount,
                    chain=chain,
                    currency=locked.currency,
                    from_address=result.from_address,
                    to_address=payment.wallet_address,
                    status="confirmed",
                    confirmations=result.confirmations,
                    block_number=result.block_number,
                )
                PaymentService.confirm_payment(locked, result.tx_hash, result.from_address, confirmations=result.confirmations)
                mark_event_processed(event_id)
                webhook_log = WebhookService.enqueue_webhook(locked)
                enqueue_webhook(webhook_log.id)
                logger.info("Payment %s confirmed tx=%s", locked.id, result.tx_hash)
        except DuplicatePaymentError:
            logger.error("Duplicate payment confirmation blocked for %s", payment.id)

    def run_batch(self, payment_id: int | None = None) -> dict:
        checked = 0
        PaymentService.expire_stale_payments()
        if payment_id is not None:
            payment = Payment.objects.filter(id=payment_id).first()
            if payment and payment.status == "pending":
                self._check_payment(payment)
                checked = 1
        else:
            for payment in Payment.objects.filter(status="pending"):
                self._check_payment(payment)
                checked += 1

        stats = {"payments_checked": checked, "payment_id": payment_id}
        try:
            stats.update(self.deliver_pending_webhooks(limit=15))
        except Exception:
            logger.exception("webhook delivery after reconcile failed")
        return stats

    def deliver_pending_webhooks(self, limit: int = 25) -> dict:
        from .models import WebhookLog

        attempted = 0
        delivered = 0
        logs = WebhookLog.objects.filter(status__in=["pending", "failed"]).order_by("created_at")[:limit]
        for log in logs:
            if not WebhookService.should_retry(log):
                continue
            attempted += 1
            WebhookService.deliver_webhook(log)
            if log.status == "delivered":
                delivered += 1
        return {"webhooks_attempted": attempted, "webhooks_delivered": delivered}

    def run_cron_cycle(self, payment_id: int | None = None) -> dict:
        payments = self.run_batch(payment_id=payment_id)
        webhooks = self.deliver_pending_webhooks()
        return {**payments, **webhooks}


_reconciler: PaymentReconciler | None = None


def get_reconciler() -> PaymentReconciler:
    global _reconciler
    if _reconciler is None:
        _reconciler = PaymentReconciler()
    return _reconciler
