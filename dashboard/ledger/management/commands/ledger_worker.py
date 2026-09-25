import logging
import time

from django.core.management.base import BaseCommand

from ledger import chain

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "TRON worker: credit confirmed deposits, send approved withdrawals from the treasury, resolve broadcast ones."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run a single pass and exit")
        parser.add_argument("--interval", type=int, default=5, help="Seconds between passes")

    def handle(self, *args, once=False, interval=5, **options):
        while True:
            stats = chain.tick()
            if any(v for v in stats.values() if not isinstance(v, bool)):
                logger.info("Ledger worker: %s", stats)
            if once:
                self.stdout.write(str(stats))
                return
            time.sleep(interval)
