"""Public read-only endpoints (no mock metrics)."""
import os

from fastapi import APIRouter

from app.config import settings
from app.services.health_service import check_blockchain, check_database

router = APIRouter(prefix="/public", tags=["public"])

_INSECURE_SECRETS = {
    "change-me-min-32-chars-for-jwt-signing",
    "change-me-min-32-chars-for-webhook-hmac",
    "change-me-32-byte-encryption-key-here",
}

_RPC_PLACEHOLDERS = ("your_key", "your_api_key", "your-alchemy", "replace-me")


@router.get("/config")
def public_config():
    """Network and security facts from server configuration — not fabricated stats."""
    return {
        "network": settings.blockchain_network,
        "currency": "ETH",
        "required_confirmations": settings.eth_required_confirmations,
        "webhook_signing": "HMAC-SHA256",
    }


@router.get("/readiness")
def transaction_readiness():
    """
    Whether the deployment can process real on-chain payments (Sepolia testnet by default).
    Use this after setting Vercel env vars to see what is still missing.
    """
    issues: list[str] = []
    db_url = settings.database_url.lower()
    rpc_url = settings.blockchain_rpc_url.lower()

    if not check_database():
        issues.append("Database unreachable — set DATABASE_URL to a cloud Postgres (e.g. Neon).")
    elif "127.0.0.1" in db_url or "localhost" in db_url:
        issues.append("DATABASE_URL points to localhost — use a hosted Postgres for production.")

    if not rpc_url or any(p in rpc_url for p in _RPC_PLACEHOLDERS):
        issues.append("BLOCKCHAIN_RPC_URL is missing or still a placeholder — use Alchemy/Infura Sepolia HTTPS URL.")
    elif not check_blockchain():
        issues.append("Blockchain RPC unreachable — check BLOCKCHAIN_RPC_URL and API key.")

    if settings.secret_key in _INSECURE_SECRETS:
        issues.append("SECRET_KEY is still the default — generate a 32+ char secret.")
    if settings.webhook_secret in _INSECURE_SECRETS:
        issues.append("WEBHOOK_SECRET is still the default — generate a 32+ char secret.")
    if settings.wallet_encryption_key in _INSECURE_SECRETS:
        issues.append("WALLET_ENCRYPTION_KEY is still the default — required to store deposit wallets.")

    cron_ok = bool((settings.cron_secret or os.getenv("CRON_SECRET") or "").strip())
    if not cron_ok and os.getenv("VERCEL"):
        issues.append(
            "CRON_SECRET not set — pending payments rely on checkout page polling until daily Vercel Cron runs."
        )

    if not settings.public_base_url or "127.0.0.1" in settings.public_base_url:
        issues.append("PUBLIC_BASE_URL should be your live site URL (e.g. https://gaxtron.vercel.app).")

    network = settings.blockchain_network.lower()
    is_testnet = network in ("sepolia", "testnet", "goerli", "holesky")
    ready = len(issues) == 0

    return {
        "ready_for_transactions": ready,
        "network": settings.blockchain_network,
        "mode": "testnet" if is_testnet else "mainnet",
        "confirmations_required": settings.eth_required_confirmations,
        "checkout_poll_reconcile": settings.checkout_reconcile_on_poll,
        "cron_configured": cron_ok,
        "issues": issues,
        "next_steps": [] if ready else issues,
        "how_to_test": [
            "Register at /register.html",
            "Create a payment in the dashboard",
            "Open the payment_url and send Sepolia ETH from a faucet wallet",
            "Status should move to confirmed after 3 blocks (checkout polls every 3s)",
        ],
    }
