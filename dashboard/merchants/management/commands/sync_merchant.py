"""Create Django + Gaxtron merchant accounts (used by merchant flow script)."""
from django.core.management.base import BaseCommand

from merchants.utils import ensure_django_user, ensure_gaxtron_merchant


class Command(BaseCommand):
    help = "Sync merchant accounts for dashboard + API (same email)"

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--username", required=True)
        parser.add_argument("--password", required=True)

    def handle(self, *args, **options):
        email = options["email"]
        username = options["username"]
        password = options["password"]
        g = ensure_gaxtron_merchant(email, username, password)
        d = ensure_django_user(email, username, password)
        self.stdout.write(self.style.SUCCESS(
            f"Gaxtron merchant id={g.id} email={g.email}; Django user id={d.id}"
        ))
