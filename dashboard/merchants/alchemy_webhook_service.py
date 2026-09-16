"""Alchemy Address Activity webhook integration — push-based deposit detection.

Optional and inert by default: without ALCHEMY_WEBHOOK_SIGNING_KEY/ALCHEMY_AUTH_TOKEN/
ALCHEMY_WEBHOOK_ID set, register_address() and verify_signature() no-op/fail safely and
run_listener's poll loop (chains.py's block-scan, now incremental — see last_scanned_block)
remains the sole detection path, same as before this integration existed.

Setup (see VERCEL.md section 7): create an Address Activity webhook in the Alchemy
dashboard pointed at POST /webhooks/alchemy/address-activity on your public URL, then set
the three env vars from that webhook's settings page.
"""
import hashlib
import hmac
import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

UPDATE_ADDRESSES_URL = "https://dashboard.alchemy.com/api/update-webhook-addresses"
REGISTER_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def is_configured() -> bool:
    return bool(settings.ALCHEMY_WEBHOOK_SIGNING_KEY and settings.ALCHEMY_AUTH_TOKEN and settings.ALCHEMY_WEBHOOK_ID)


def verify_signature(raw_body: bytes, signature: str | None) -> bool:
    if not settings.ALCHEMY_WEBHOOK_SIGNING_KEY or not signature:
        return False
    expected = hmac.new(settings.ALCHEMY_WEBHOOK_SIGNING_KEY.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def register_address(address: str) -> None:
    """Tell Alchemy to start watching a newly-created deposit address. Best-effort: if this
    fails or isn't configured, the address is simply never pushed to us and falls back to
    the normal poll loop — no payment is ever missed because of this call failing."""
    if not settings.ALCHEMY_AUTH_TOKEN or not settings.ALCHEMY_WEBHOOK_ID:
        return
    try:
        httpx.patch(
            UPDATE_ADDRESSES_URL,
            json={
                "webhook_id": settings.ALCHEMY_WEBHOOK_ID,
                "addresses_to_add": [address],
                "addresses_to_remove": [],
            },
            headers={"X-Alchemy-Token": settings.ALCHEMY_AUTH_TOKEN, "Content-Type": "application/json"},
            timeout=REGISTER_TIMEOUT,
        ).raise_for_status()
    except Exception:
        logger.warning("Failed to register %s with Alchemy Address Activity webhook — will rely on polling", address)
