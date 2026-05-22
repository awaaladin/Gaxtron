import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.core.exceptions import DuplicatePaymentError
from app.core.url_validation import CallbackUrlError, validate_callback_url
from app.db.models.payment import Payment
from app.schemas.payment import CreatePaymentRequest
from app.services.wallet_service import WalletService

logger = logging.getLogger(__name__)

ETH_CHAIN = "ETH"
ETH_CURRENCY = "ETH"


class PaymentService:
    @staticmethod
    def build_payment_url(payment_id: int) -> str:
        return settings.payment_url(payment_id)

    @staticmethod
    def create_payment(db: Session, user_id: int, data: CreatePaymentRequest) -> Payment:
        try:
            validate_callback_url(str(data.callback_url))
        except CallbackUrlError as e:
            raise ValueError(str(e)) from e

        if data.idempotency_key:
            existing = (
                db.query(Payment)
                .filter(
                    Payment.idempotency_key == data.idempotency_key,
                    Payment.user_id == user_id,
                )
                .with_for_update()
                .first()
            )
            if existing:
                logger.info("Idempotent payment hit: %s", existing.id)
                return existing

        wallet = WalletService.generate_wallet(db, ETH_CHAIN, ETH_CURRENCY, user_id=user_id)
        event_id = str(uuid.uuid4())
        expires_at = datetime.utcnow() + timedelta(minutes=settings.payment_expiry_minutes)

        payment = Payment(
            user_id=user_id,
            amount=data.amount,
            chain=ETH_CHAIN,
            currency=ETH_CURRENCY,
            status="pending",
            wallet_address=wallet.address,
            callback_url=str(data.callback_url),
            idempotency_key=data.idempotency_key,
            event_id=event_id,
            expires_at=expires_at,
            confirmations=0,
        )
        db.add(payment)
        db.flush()
        wallet.payment_id = payment.id
        db.flush()

        logger.info(
            "ETH payment %s created user=%s amount=%s url=%s",
            payment.id,
            user_id,
            payment.amount,
            PaymentService.build_payment_url(payment.id),
        )
        return payment

    @staticmethod
    def get_payment(db: Session, payment_id: int, user_id: int | None = None) -> Payment | None:
        q = db.query(Payment).filter(Payment.id == payment_id)
        if user_id is not None:
            q = q.filter(Payment.user_id == user_id)
        return q.first()

    @staticmethod
    def get_payment_for_update(db: Session, payment_id: int) -> Payment | None:
        return (
            db.query(Payment)
            .filter(Payment.id == payment_id)
            .with_for_update()
            .first()
        )

    @staticmethod
    def expire_stale_payments(db: Session) -> int:
        now = datetime.utcnow()
        stale = (
            db.query(Payment)
            .filter(
                Payment.status == "pending",
                Payment.expires_at.isnot(None),
                Payment.expires_at < now,
            )
            .all()
        )
        for payment in stale:
            payment.status = "failed"
            logger.info("Payment %s expired", payment.id)
        return len(stale)

    @staticmethod
    def confirm_payment(
        db: Session,
        payment: Payment,
        tx_hash: str,
        from_address: str = "unknown",
        confirmations: int = 0,
    ) -> Payment:
        if payment.status == "confirmed":
            if payment.tx_hash == tx_hash:
                return payment
            raise DuplicatePaymentError()

        if payment.status != "pending":
            raise DuplicatePaymentError()

        payment.status = "confirmed"
        payment.tx_hash = tx_hash
        payment.confirmations = confirmations
        payment.confirmed_at = datetime.utcnow()
        db.flush()
        logger.info("Payment %s confirmed tx=%s confirmations=%s", payment.id, tx_hash, confirmations)
        return payment

    @staticmethod
    def fail_payment(db: Session, payment: Payment) -> Payment:
        if payment.status == "pending":
            payment.status = "failed"
            db.flush()
        return payment

    @staticmethod
    def update_pending_confirmations(db: Session, payment: Payment, tx_hash: str, confirmations: int) -> Payment:
        """Track tx seen before full confirmation (checkout UI)."""
        if payment.status == "pending" and tx_hash:
            payment.tx_hash = tx_hash
            payment.confirmations = confirmations
            db.flush()
        return payment
