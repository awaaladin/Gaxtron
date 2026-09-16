"""
Health/readiness and public config endpoints — ported from GaX/app/main.py's inline health
routes and GaX/app/api/routers/public.py.
"""
import os

from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView

from .health_service import check_all_chains, check_blockchain, check_blockchain_errors, check_database, check_redis

_INSECURE_SECRETS = {
    "change-me-min-32-chars-for-jwt-signing-abc123",
    "change-me-min-32-chars-for-webhook-hmac-abc",
    "change-me-32-byte-encryption-key-here!!",
    "django-insecure-change-me",
}
_RPC_PLACEHOLDERS = ("your_key", "your_api_key", "your-alchemy", "replace-me")


class HealthView(APIView):
    def get(self, request):
        db_ok = check_database()
        redis_ok = check_redis()
        chains = check_all_chains()
        chain_errors = {c: e for c, e in check_blockchain_errors().items() if e}
        return Response({
            "status": "ok" if db_ok else "degraded",
            "service": "gaxtron-api",
            "env": os.getenv("ENV", "development"),
            "checks": {"database": db_ok, "redis": redis_ok, "chains": chains, "chain_errors": chain_errors},
        })


class ReadyView(APIView):
    def get(self, request):
        if not check_database():
            return Response({"status": "not_ready", "database": False}, status=503)
        return Response({"status": "ready", "database": True, "redis": check_redis(), "blockchain": check_blockchain()})


class LiveView(APIView):
    def get(self, request):
        return Response({"status": "alive"})


class PublicConfigView(APIView):
    def get(self, request):
        return Response({
            "network": settings.BLOCKCHAIN_NETWORK,
            "currency": "ETH",
            "required_confirmations": settings.ETH_REQUIRED_CONFIRMATIONS,
            "webhook_signing": "HMAC-SHA256",
        })


class ReadinessView(APIView):
    """Whether the deployment can process real on-chain payments — not fabricated stats."""

    def get(self, request):
        issues: list[str] = []
        db_url = os.getenv("DATABASE_URL", "").lower()
        rpc_url = settings.BLOCKCHAIN_RPC_URL.lower()

        if not check_database():
            issues.append("Database unreachable — set DATABASE_URL to a cloud Postgres (e.g. Neon).")
        elif "127.0.0.1" in db_url or "localhost" in db_url:
            issues.append("DATABASE_URL points to localhost — use a hosted Postgres for production.")

        if not rpc_url or any(p in rpc_url for p in _RPC_PLACEHOLDERS):
            issues.append("BLOCKCHAIN_RPC_URL is missing or still a placeholder — use an Alchemy/Infura Sepolia HTTPS URL.")
        elif not check_blockchain():
            errors = check_blockchain_errors()
            detail = "; ".join(f"{c}: {e}" for c, e in errors.items() if e) or "no reachable chain RPC"
            issues.append(f"Blockchain RPC unreachable — check BLOCKCHAIN_RPC_URL and API key. ({detail})")

        if settings.JWT_SECRET_KEY in _INSECURE_SECRETS:
            issues.append("SECRET_KEY is still the default — generate a 32+ char secret.")
        if settings.WEBHOOK_SECRET in _INSECURE_SECRETS:
            issues.append("WEBHOOK_SECRET is still the default — generate a 32+ char secret.")
        if settings.WALLET_ENCRYPTION_KEY in _INSECURE_SECRETS:
            issues.append("WALLET_ENCRYPTION_KEY is still the default — required to store deposit wallets.")
        if settings.SECRET_KEY in _INSECURE_SECRETS:
            issues.append("DJANGO_SECRET_KEY is still the default — generate a 32+ char secret (used for sessions/CSRF).")

        cron_ok = bool((settings.CRON_SECRET or os.getenv("CRON_SECRET") or "").strip())
        if not cron_ok and os.getenv("VERCEL"):
            issues.append("CRON_SECRET not set — pending payments rely on checkout-page polling until daily Vercel Cron runs.")

        if not settings.PUBLIC_BASE_URL or "127.0.0.1" in settings.PUBLIC_BASE_URL:
            issues.append("PUBLIC_BASE_URL should be your live site URL (e.g. https://gaxtron.vercel.app).")

        network = settings.BLOCKCHAIN_NETWORK.lower()
        is_testnet = network in ("sepolia", "testnet", "goerli", "holesky")
        ready = len(issues) == 0

        return Response({
            "ready_for_transactions": ready,
            "network": settings.BLOCKCHAIN_NETWORK,
            "mode": "testnet" if is_testnet else "mainnet",
            "confirmations_required": settings.ETH_REQUIRED_CONFIRMATIONS,
            "checkout_poll_reconcile": settings.CHECKOUT_RECONCILE_ON_POLL,
            "cron_configured": cron_ok,
            "issues": issues,
            "next_steps": [] if ready else issues,
            "how_to_test": [
                "Register at /register/",
                "Create a payment on the Payments page",
                "Open the payment_url and send Sepolia ETH from a faucet wallet",
                "Status should move to confirmed after 3 blocks (checkout polls every 3s)",
            ],
        })
