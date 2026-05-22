import asyncio
import json
import logging
import time
from datetime import datetime

import redis

from app.config import settings
from app.chains.base import IncomingPaymentResult
from app.core.exceptions import DuplicatePaymentError
from app.db.models.payment import Payment
from app.db.models.transaction import Transaction
from app.db.session import SessionLocal
from app.services.payment_processor import get_payment_processor
from app.services.payment_service import PaymentService
from app.services.webhook_service import WebhookService
from app.workers.queue import (
    QUEUE_PAYMENT_EVENTS,
    QUEUE_WEBHOOK_DELIVERY,
    enqueue_webhook,
    get_redis,
    is_event_processed,
    mark_event_processed,
)

logger = logging.getLogger(__name__)


class BlockchainListener:
    """Sepolia ETH worker — detect tx, wait for confirmations, webhook."""

    def __init__(self):
        self.processor = get_payment_processor()

    def process_pending_payments(self) -> None:
        db = SessionLocal()
        try:
            PaymentService.expire_stale_payments(db)
            pending = db.query(Payment).filter(Payment.status == "pending").all()
            for payment in pending:
                self._check_payment(db, payment)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Error processing pending payments")
        finally:
            db.close()

    def _check_payment(self, db, payment: Payment) -> None:
        if payment.status != "pending":
            return

        if payment.expires_at and payment.expires_at < datetime.utcnow():
            PaymentService.fail_payment(db, payment)
            return

        chain = getattr(payment, "chain", None) or "ETH"
        try:
            if payment.tx_hash:
                confirmations = self.processor.get_confirmations(chain, payment.tx_hash)
                PaymentService.update_pending_confirmations(db, payment, payment.tx_hash, confirmations)
                if confirmations >= settings.eth_required_confirmations:
                    result = IncomingPaymentResult(
                        tx_hash=payment.tx_hash,
                        from_address="unknown",
                        confirmations=confirmations,
                    )
                    self._finalize_payment(db, payment, result, chain)
                return

            result = self.processor.detect_payment(
                chain, payment.wallet_address, payment.amount, payment.currency
            )
        except Exception:
            logger.exception("detect_payment failed payment=%s chain=%s", payment.id, chain)
            return

        if not result:
            return

        required = settings.eth_required_confirmations
        if result.confirmations < required:
            PaymentService.update_pending_confirmations(
                db, payment, result.tx_hash, result.confirmations
            )
            logger.info(
                "Payment %s tx seen %s (%s/%s confirmations)",
                payment.id,
                result.tx_hash[:16],
                result.confirmations,
                required,
            )
            return

        self._finalize_payment(db, payment, result, chain)

    def _finalize_payment(self, db, payment: Payment, result, chain: str) -> None:
        event_id = f"{chain}_{result.tx_hash}"
        if is_event_processed(event_id):
            logger.info("Skipping duplicate event %s", event_id)
            return

        existing_tx = db.query(Transaction).filter(Transaction.tx_hash == result.tx_hash).first()
        if existing_tx:
            mark_event_processed(event_id)
            return

        locked = PaymentService.get_payment_for_update(db, payment.id)
        if not locked or locked.status != "pending":
            return

        try:
            tx_record = Transaction(
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
            db.add(tx_record)
            PaymentService.confirm_payment(
                db,
                locked,
                result.tx_hash,
                result.from_address,
                confirmations=result.confirmations,
            )
            mark_event_processed(event_id)
            webhook_log = WebhookService.enqueue_webhook(db, locked)
            enqueue_webhook(webhook_log.id)
            logger.info("Payment %s confirmed tx=%s", locked.id, result.tx_hash)
        except DuplicatePaymentError:
            db.rollback()
            logger.error("Duplicate payment confirmation blocked for %s", payment.id)

    def process_queue_event(self, raw: str) -> None:
        data = json.loads(raw)
        payment_id = data.get("payment_id")
        if not payment_id:
            return
        db = SessionLocal()
        try:
            payment = db.query(Payment).filter(Payment.id == payment_id).first()
            if payment and payment.status == "pending":
                self._check_payment(db, payment)
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Queue event processing failed")
        finally:
            db.close()

    async def process_webhook_queue(self) -> None:
        from app.db.models.webhook_log import WebhookLog

        r = get_redis()
        raw = r.brpop(QUEUE_WEBHOOK_DELIVERY, timeout=5)
        if not raw:
            return
        data = json.loads(raw[1])
        webhook_log_id = data.get("webhook_log_id")
        if not webhook_log_id:
            return

        db = SessionLocal()
        try:
            log = db.query(WebhookLog).filter(WebhookLog.id == webhook_log_id).first()
            if log and WebhookService.should_retry(log):
                await WebhookService.deliver_webhook(db, log)
                if WebhookService.should_retry(log):
                    delay = settings.webhook_retry_base_seconds * (2 ** (log.attempts - 1))
                    await asyncio.sleep(min(delay, 300))
                    enqueue_webhook(log.id)
        finally:
            db.close()

    def _redis_client(self):
        while True:
            try:
                client = get_redis()
                client.ping()
                return client
            except Exception:
                logger.warning("Waiting for Redis at %s...", settings.redis_url)
                time.sleep(3)

    async def run(self) -> None:
        health = self.processor.chain_health()
        logger.info("ETH listener started (Sepolia): %s", health)
        r = self._redis_client()
        while True:
            try:
                self.process_pending_payments()
                try:
                    raw = r.brpop(QUEUE_PAYMENT_EVENTS, timeout=2)
                    if raw:
                        self.process_queue_event(raw[1])
                except redis.RedisError:
                    logger.warning("Redis connection lost, reconnecting...")
                    r = self._redis_client()
                await self.process_webhook_queue()
            except Exception:
                logger.exception("Listener loop error")
            await asyncio.sleep(5)
