from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models.payment import Payment
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.db.models.webhook_log import WebhookLog
from app.config import settings
from app.db.session import get_db
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def dashboard_stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    payments = db.query(Payment).filter(Payment.user_id == user.id)
    total = payments.count()
    confirmed = payments.filter(Payment.status == "confirmed").count()
    failed = payments.filter(Payment.status == "failed").count()
    pending = payments.filter(Payment.status == "pending").count()
    revenue = (
        db.query(func.coalesce(func.sum(Payment.amount), 0))
        .filter(Payment.user_id == user.id, Payment.status == "confirmed")
        .scalar()
    )
    return {
        "total_payments": total,
        "successful": confirmed,
        "failed": failed,
        "pending": pending,
        "revenue": str(revenue or Decimal("0")),
        "success_rate": round((confirmed / total * 100) if total else 0, 1),
    }


@router.get("/transactions")
def list_transactions(
    status: str | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Transaction).filter(Transaction.user_id == user.id)
    if status:
        q = q.filter(Transaction.status == status)
    rows = q.order_by(Transaction.created_at.desc()).limit(100).all()
    return [
        {
            "id": t.id,
            "tx_hash": t.tx_hash,
            "amount": str(t.amount),
            "currency": t.currency,
            "status": t.status,
            "confirmations": t.confirmations,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]


@router.get("/payments")
def list_payments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (
        db.query(Payment)
        .filter(Payment.user_id == user.id)
        .order_by(Payment.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": p.id,
            "amount": str(p.amount),
            "currency": p.currency,
            "chain": p.chain,
            "status": p.status,
            "wallet_address": p.wallet_address,
            "tx_hash": p.tx_hash,
            "confirmations": p.confirmations or 0,
            "payment_url": PaymentService.build_payment_url(p),
            "public_token": p.public_token,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "confirmed_at": p.confirmed_at.isoformat() if p.confirmed_at else None,
        }
        for p in rows
    ]


@router.get("/webhooks/logs")
def webhook_logs(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    payment_ids = [p.id for p in db.query(Payment.id).filter(Payment.user_id == user.id).all()]
    if not payment_ids:
        return []
    logs = (
        db.query(WebhookLog)
        .filter(WebhookLog.payment_id.in_(payment_ids))
        .order_by(WebhookLog.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": l.id,
            "payment_id": l.payment_id,
            "event_id": l.event_id,
            "status": l.status,
            "response_code": l.response_code,
            "attempts": l.attempts,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]
