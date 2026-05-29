"""
Public checkout — customer-facing payment page (Sepolia ETH).
"""
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.schemas.payment import PublicPaymentStatus
from app.services.payment_service import PaymentService
from app.services.reconcile_service import get_reconciler

router = APIRouter(tags=["checkout"])


def _canonical_pay_path(payment_ref: str) -> str:
    return f"/pay/{payment_ref}"


def _serve_checkout_page(payment_ref: str, db: Session):
    """Hosted Gaxtron checkout — customer pays via link or QR."""
    payment = PaymentService.get_payment_by_ref(db, payment_ref)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    pay_html = os.path.join(_frontend_dir(), "pay.html")
    if os.path.isfile(pay_html):
        return FileResponse(pay_html, media_type="text/html")

    return HTMLResponse(_fallback_checkout_html(payment_ref))

def _frontend_dir() -> str:
    here = os.path.dirname(__file__)
    for rel in ("..", "..", "..", ".."), ("..", "..", ".."):
        path = os.path.abspath(os.path.join(here, *rel, "frontend"))
        if os.path.isdir(path):
            return path
    return os.path.abspath(os.path.join(here, "..", "..", "..", "..", "frontend"))


@router.get("/payment/{payment_ref}", response_model=PublicPaymentStatus)
def get_payment_status(payment_ref: str, db: Session = Depends(get_db)):
    """Public status for checkout polling (no auth). Re-checks chain when still pending."""
    payment = PaymentService.get_payment_by_ref(db, payment_ref)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if settings.checkout_reconcile_on_poll and payment.status == "pending":
        try:
            get_reconciler().run_batch(payment_id=payment.id)
            db.refresh(payment)
        except Exception:
            pass  # status poll should not fail if RPC is slow
    return PublicPaymentStatus(
        id=payment.id,
        public_token=payment.public_token,
        amount=payment.amount,
        currency=payment.currency,
        chain=payment.chain,
        status=payment.status,
        wallet_address=payment.wallet_address,
        address=payment.wallet_address,
        tx_hash=payment.tx_hash,
        confirmations=payment.confirmations or 0,
        required_confirmations=settings.eth_required_confirmations,
        network=settings.blockchain_network,
        created_at=payment.created_at,
        confirmed_at=payment.confirmed_at,
        expires_at=payment.expires_at,
    )


@router.get("/checkout/{payment_ref}")
def checkout_redirect(payment_ref: str):
    """Merchant-friendly alias — redirects to hosted payment page."""
    return RedirectResponse(url=_canonical_pay_path(payment_ref), status_code=302)


@router.get("/link/{payment_ref}")
def payment_link_redirect(payment_ref: str):
    """Short payment link for SMS, email, or QR (same hosted checkout)."""
    return RedirectResponse(url=_canonical_pay_path(payment_ref), status_code=302)


@router.get("/pay")
def pay_query_redirect(
    ref: str | None = Query(None),
    token: str | None = Query(None),
    payment: str | None = Query(None),
):
    """Support ?ref=pay_xxx when merchants embed query-style links."""
    payment_ref = ref or token or payment
    if not payment_ref:
        raise HTTPException(status_code=400, detail="Missing payment reference (?ref=pay_…)")
    return RedirectResponse(url=_canonical_pay_path(payment_ref), status_code=302)


@router.get("/pay/{payment_ref}")
def checkout_page(payment_ref: str, db: Session = Depends(get_db)):
    """Hosted checkout — customer opens this link (or scans QR) to pay on Gaxtron."""
    return _serve_checkout_page(payment_ref, db)


def _fallback_checkout_html(payment_ref: str) -> str:
    return f"""<!DOCTYPE html><html><body><p>Loading payment…</p>
    <script>location.replace('/pay/{payment_ref}');</script></body></html>"""
