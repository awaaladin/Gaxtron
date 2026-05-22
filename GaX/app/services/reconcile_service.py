"""
Payment reconciliation — used by Vercel Cron and checkout polling.
"""
import asyncio
import logging

from app.db.models.payment import Payment
from app.db.models.webhook_log import WebhookLog
from app.db.session import SessionLocal
from app.services.payment_service import PaymentService
from app.services.webhook_service import WebhookService
from app.workers.listener import BlockchainListener

logger = logging.getLogger(__name__)


class PaymentReconciler:
    def __init__(self):
        self._listener = BlockchainListener()

    def run_batch(self, payment_id: int | None = None) -> dict:
        """Process pending payments (all or one). Returns summary stats."""
        db = SessionLocal()
        checked = 0
        try:
            PaymentService.expire_stale_payments(db)
            if payment_id is not None:
                payment = db.query(Payment).filter(Payment.id == payment_id).first()
                if payment and payment.status == "pending":
                    self._listener._check_payment(db, payment)
                    checked = 1
            else:
                pending = db.query(Payment).filter(Payment.status == "pending").all()
                for payment in pending:
                    self._listener._check_payment(db, payment)
                    checked += 1
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("reconcile batch failed")
            raise
        finally:
            db.close()

        stats = {"payments_checked": checked, "payment_id": payment_id}
        try:
            stats.update(asyncio.run(self.deliver_pending_webhooks(limit=15)))
        except Exception:
            logger.exception("webhook delivery after reconcile failed")
        return stats

    async def deliver_pending_webhooks(self, limit: int = 25) -> dict:
        """Deliver queued webhooks without Redis (for serverless cron)."""
        db = SessionLocal()
        attempted = 0
        delivered = 0
        try:
            logs = (
                db.query(WebhookLog)
                .filter(WebhookLog.status.in_(["pending", "failed"]))
                .order_by(WebhookLog.created_at.asc())
                .limit(limit)
                .all()
            )
            for log in logs:
                if not WebhookService.should_retry(log):
                    continue
                attempted += 1
                await WebhookService.deliver_webhook(db, log)
                if log.status == "delivered":
                    delivered += 1
        finally:
            db.close()
        return {"webhooks_attempted": attempted, "webhooks_delivered": delivered}

    def run_cron_cycle(self, payment_id: int | None = None) -> dict:
        """Full cron tick: reconcile payments + deliver webhooks."""
        payments = self.run_batch(payment_id=payment_id)
        webhooks = asyncio.run(self.deliver_pending_webhooks())
        return {**payments, **webhooks}


_reconciler: PaymentReconciler | None = None


def get_reconciler() -> PaymentReconciler:
    global _reconciler
    if _reconciler is None:
        _reconciler = PaymentReconciler()
    return _reconciler
