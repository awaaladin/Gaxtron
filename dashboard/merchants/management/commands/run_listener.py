"""
Background worker — ported from GaX/app/workers/{listener,runner}.py. Simplified to a plain
poll loop: since merchants/webhook_service.py already delivers webhooks synchronously (no
asyncio needed once httpx.AsyncClient became httpx.Client), the original's Redis BRPOP "low
latency nudge" queue is just an optimization on top of the same polling this loop already
does every cycle — dropping it keeps this equivalent to how GaX behaved whenever Redis was
unavailable anyway (its own documented fallback path), at a fraction of the code.

Run with: python manage.py run_listener
"""
import logging
import time

from django.core.management.base import BaseCommand

from merchants.reconcile_service import get_reconciler

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 5


class Command(BaseCommand):
    help = "Poll pending payments for on-chain confirmations and deliver webhooks (ETH/Sepolia)."

    def handle(self, *args, **options):
        reconciler = get_reconciler()
        health = reconciler.processor.chain_health()
        self.stdout.write(self.style.SUCCESS(f"Gaxtron listener started: {health}"))

        while True:
            try:
                stats = reconciler.run_batch()
                if stats.get("payments_checked") or stats.get("webhooks_attempted"):
                    logger.info("Reconcile tick: %s", stats)
            except Exception:
                logger.exception("Listener loop error")
            time.sleep(POLL_INTERVAL_SECONDS)
