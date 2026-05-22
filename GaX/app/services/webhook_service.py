import json
import logging
import uuid
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import sign_webhook_payload
from app.core.url_validation import validate_callback_url
from app.db.models.payment import Payment
from app.db.models.webhook_log import WebhookLog

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class WebhookService:
    @staticmethod
    def build_payload(payment: Payment) -> dict:
        return {
            "status": "confirmed",
            "payment_id": payment.id,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "chain": getattr(payment, "chain", "ETH"),
            "tx_hash": payment.tx_hash,
            "wallet_address": payment.wallet_address,
            "confirmations": payment.confirmations or 0,
            "confirmed_at": payment.confirmed_at.isoformat() if payment.confirmed_at else None,
        }

    @staticmethod
    def enqueue_webhook(db: Session, payment: Payment) -> WebhookLog:
        event_id = f"wh_{payment.event_id or payment.id}"
        existing = db.query(WebhookLog).filter(WebhookLog.event_id == event_id).first()
        if existing:
            return existing

        payload = WebhookService.build_payload(payment)
        log = WebhookLog(
            payment_id=payment.id,
            event_id=event_id,
            callback_url=payment.callback_url,
            payload=json.dumps(payload),
            status="pending",
        )
        db.add(log)
        db.flush()
        return log

    @staticmethod
    def should_retry(log: WebhookLog) -> bool:
        return log.status in ("pending", "failed") and log.attempts < settings.webhook_max_attempts

    @staticmethod
    async def deliver_webhook(db: Session, log: WebhookLog) -> WebhookLog:
        if not WebhookService.should_retry(log):
            return log

        try:
            validate_callback_url(log.callback_url)
        except Exception as e:
            log.attempts += 1
            log.status = "failed"
            log.response_body = f"Blocked URL: {e}"[:2000]
            db.commit()
            return log

        payload = json.loads(log.payload)
        signature = sign_webhook_payload(payload)

        try:
            async with httpx.AsyncClient(
                timeout=WEBHOOK_TIMEOUT,
                follow_redirects=False,
                limits=httpx.Limits(max_connections=10),
            ) as client:
                response = await client.post(
                    log.callback_url,
                    json=payload,
                    headers={
                        "X-Gaxtron-Signature": signature,
                        "X-Gaxtron-Event": payload.get("event", "payment.confirmed"),
                        "Content-Type": "application/json",
                        "User-Agent": "Gaxtron-Webhook/2.0",
                    },
                )
            log.response_code = response.status_code
            log.response_body = response.text[:2000]
            log.attempts += 1

            if 200 <= response.status_code < 300:
                log.status = "delivered"
                log.delivered_at = datetime.utcnow()
                logger.info("Webhook delivered for payment %s", log.payment_id)
            else:
                log.status = "failed"
                logger.warning(
                    "Webhook HTTP %s for payment %s (attempt %s)",
                    response.status_code,
                    log.payment_id,
                    log.attempts,
                )
        except httpx.HTTPError as e:
            log.attempts += 1
            log.status = "failed"
            log.response_body = str(e)[:2000]
            logger.warning("Webhook delivery error payment %s attempt %s: %s", log.payment_id, log.attempts, e)

        db.commit()
        return log
