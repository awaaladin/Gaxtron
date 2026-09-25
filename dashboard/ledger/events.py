"""Signed outbound webhooks to platforms, delivered at-least-once from a DB outbox.

emit() writes a WebhookEvent in the caller's transaction, so an event exists if and only if
the ledger change committed. deliver_pending() is called from the reconcile loop.
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import timedelta

import httpx
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from merchants.url_validation import validate_callback_url

from .models import PlatformConfig, WebhookEvent

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def sign(secret: str, timestamp: int, body: str) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256).hexdigest()


def emit(platform, event_type: str, data) -> WebhookEvent | None:
    config = PlatformConfig.objects.filter(platform=platform).first()
    if not config or not config.webhook_url:
        return None
    event = WebhookEvent(platform=platform, type=event_type)
    event.payload = json.dumps(
        {"id": event.event_id, "type": event_type, "created": int(time.time()), "data": data}, default=str
    )
    event.save()
    return event


def deliver_pending(limit: int = 25) -> dict:
    now = timezone.now()
    due = (
        WebhookEvent.objects.filter(
            Q(status=WebhookEvent.Status.PENDING) | Q(status=WebhookEvent.Status.FAILED),
            attempts__lt=settings.WEBHOOK_MAX_ATTEMPTS,
            next_attempt_at__lte=now,
        )
        .select_related("platform")
        .order_by("id")[:limit]
    )
    attempted = delivered = 0
    for event in due:
        backoff = timedelta(seconds=settings.WEBHOOK_RETRY_BASE_SECONDS * (2**event.attempts))
        claimed = WebhookEvent.objects.filter(pk=event.pk, attempts=event.attempts).update(
            attempts=event.attempts + 1, next_attempt_at=now + backoff
        )
        if not claimed:
            continue
        attempted += 1
        if _deliver(event):
            delivered += 1
    return {"platform_events_attempted": attempted, "platform_events_delivered": delivered}


def _deliver(event: WebhookEvent) -> bool:
    config = PlatformConfig.objects.filter(platform=event.platform).first()
    if not config or not config.webhook_url:
        _finish(event, WebhookEvent.Status.FAILED, None, "No webhook URL configured", final=True)
        return False
    try:
        validate_callback_url(config.webhook_url)
    except ValueError as exc:
        _finish(event, WebhookEvent.Status.FAILED, None, f"Blocked URL: {exc}", final=True)
        return False

    timestamp = int(time.time())
    try:
        response = httpx.post(
            config.webhook_url,
            content=event.payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Gaxtron-Webhook/3.0",
                "X-Gaxtron-Event": event.type,
                "X-Gaxtron-Signature": f"t={timestamp},v1={sign(config.signing_secret, timestamp, event.payload)}",
            },
            timeout=TIMEOUT,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        _finish(event, WebhookEvent.Status.FAILED, None, str(exc))
        return False

    ok = 200 <= response.status_code < 300
    _finish(event, WebhookEvent.Status.DELIVERED if ok else WebhookEvent.Status.FAILED, response.status_code, response.text)
    return ok


def _finish(event, status, code, body, final=False):
    fields = {"status": status, "response_code": code, "response_body": (body or "")[:2000]}
    if status == WebhookEvent.Status.DELIVERED:
        fields["delivered_at"] = timezone.now()
    if final:
        fields["attempts"] = settings.WEBHOOK_MAX_ATTEMPTS
    WebhookEvent.objects.filter(pk=event.pk).update(**fields)
