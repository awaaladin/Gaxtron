from django.apps import AppConfig


class LedgerConfig(AppConfig):
    name = "ledger"

    def ready(self):
        from . import schema  # noqa: F401  (registers the X-API-Key OpenAPI security scheme)
