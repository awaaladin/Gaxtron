import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_api_key
from app.core.exceptions import AppError, to_http_exception
from app.config import settings
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.payment import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    PaymentResponse,
    VerifyPaymentResponse,
)
from app.services.payment_service import PaymentService
from app.workers.queue import enqueue_payment_check

logger = logging.getLogger(__name__)
router = APIRouter(tags=["payments"])


def _to_create_response(payment) -> CreatePaymentResponse:
    return CreatePaymentResponse(
        payment_id=payment.id,
        payment_token=payment.public_token or str(payment.id),
        payment_url=PaymentService.build_payment_url(payment),
        wallet_address=payment.wallet_address,
        amount=payment.amount,
        currency=payment.currency,
        chain=payment.chain,
        status=payment.status,
        callback_url=payment.callback_url,
        tx_hash=payment.tx_hash,
        confirmations=payment.confirmations or 0,
        created_at=payment.created_at,
        expires_at=payment.expires_at,
    )


def _to_payment_response(payment) -> PaymentResponse:
    return PaymentResponse(
        id=payment.id,
        amount=payment.amount,
        chain=payment.chain,
        currency=payment.currency,
        status=payment.status,
        wallet_address=payment.wallet_address,
        callback_url=payment.callback_url,
        tx_hash=payment.tx_hash,
        confirmations=payment.confirmations or 0,
        payment_url=PaymentService.build_payment_url(payment),
        created_at=payment.created_at,
        confirmed_at=payment.confirmed_at,
        expires_at=payment.expires_at,
    )


@router.post("/create-payment", response_model=CreatePaymentResponse, status_code=status.HTTP_201_CREATED)
def create_payment(
    data: CreatePaymentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api_key),
):
    """Create Sepolia ETH payment and return shareable checkout link."""
    try:
        payment = PaymentService.create_payment(db, user.id, data)
        db.commit()
        db.refresh(payment)
        enqueue_payment_check(payment.id)
        logger.info("Payment %s url=%s", payment.id, PaymentService.build_payment_url(payment))
        return _to_create_response(payment)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except AppError as e:
        db.rollback()
        raise to_http_exception(e) from e
    except Exception:
        db.rollback()
        logger.exception("create_payment failed for user %s", user.id)
        raise HTTPException(status_code=500, detail="Failed to create payment")


@router.get("/payment/{payment_id}/merchant", response_model=PaymentResponse)
def get_payment_merchant(
    payment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api_key),
):
    """Merchant-authenticated payment detail."""
    payment = PaymentService.get_payment(db, payment_id, user.id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return _to_payment_response(payment)


@router.get("/verify-payment/{payment_id}", response_model=VerifyPaymentResponse)
def verify_payment(
    payment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_api_key),
):
    payment = PaymentService.get_payment(db, payment_id, user.id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return VerifyPaymentResponse(
        id=payment.id,
        status=payment.status,
        amount=payment.amount,
        chain=payment.chain,
        currency=payment.currency,
        wallet_address=payment.wallet_address,
        tx_hash=payment.tx_hash,
        confirmations=payment.confirmations or 0,
        payment_url=PaymentService.build_payment_url(payment),
        confirmed_at=payment.confirmed_at,
        expires_at=payment.expires_at,
    )
