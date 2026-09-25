from django.core.management.base import BaseCommand, CommandError

from ledger import services


class Command(BaseCommand):
    help = "Verify ledger invariants (balanced transactions, balances == entries, escrow/withdrawal holds). Exits non-zero on any problem — run it on a schedule and alert on failure."

    def handle(self, *args, **options):
        problems = services.reconcile()
        if problems:
            for problem in problems:
                self.stderr.write(self.style.ERROR(problem))
            raise CommandError(f"{len(problems)} ledger problem(s) found")
        self.stdout.write(self.style.SUCCESS("Ledger is consistent."))
