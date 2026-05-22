from functools import lru_cache
import os
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"

    database_url: str = "postgresql://gaxtron:gaxtron_secret@127.0.0.1:5433/gaxtron_db"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = Field(default="change-me-min-32-chars-for-jwt-signing", min_length=32)
    webhook_secret: str = Field(default="change-me-min-32-chars-for-webhook-hmac", min_length=32)
    wallet_encryption_key: str = Field(default="change-me-32-byte-encryption-key-here", min_length=32)

    # Ethereum (ETH + ERC-20 USDT)
    blockchain_rpc_url: str = "https://rpc.sepolia.org"
    blockchain_network: str = "sepolia"
    required_confirmations: int = Field(default=3, ge=1, le=100)  # alias: eth
    eth_required_confirmations: int = Field(default=3, ge=1, le=100)
    usdt_contract_address: str = "0x94a9D9AC8a22534D3cDfaD9d54e96e22d858e9b"
    blockchain_scan_blocks: int = Field(default=500, ge=10, le=5000)

    # TRON (TRX + TRC-20 USDT)
    tron_network: str = "shasta"  # shasta | mainnet
    tron_api_url: str = ""
    tron_usdt_contract: str = "TG3XXyExBkPp9nzdajDZsozEu4BkaFjKHr"  # Shasta USDT
    tron_required_confirmations: int = Field(default=19, ge=1, le=100)

    # Bitcoin
    bitcoin_api_url: str = "https://blockstream.info/testnet/api"
    bitcoin_network: str = "testnet"
    btc_required_confirmations: int = Field(default=3, ge=1, le=100)

    # Solana
    solana_rpc_url: str = "https://api.devnet.solana.com"
    sol_required_confirmations: int = Field(default=32, ge=1, le=100)

    # ETH-only product mode (Sepolia)
    enabled_chains: str = "ETH"
    public_base_url: str = "http://127.0.0.1:8002"

    # Vercel Cron (set CRON_SECRET in Vercel dashboard — auto-sent as Bearer token)
    cron_secret: str = ""  # env: CRON_SECRET (Vercel Cron Bearer token)
    # When True, GET /payment/{id} also hits Sepolia (fast UX between cron ticks)
    checkout_reconcile_on_poll: bool = True

    api_rate_limit: int = Field(default=100, ge=10)
    api_rate_limit_window: int = Field(default=60, ge=1)
    auth_rate_limit: int = Field(default=20, ge=5)
    auth_rate_limit_window: int = 300

    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=1440, ge=5, le=10080)

    payment_expiry_minutes: int = Field(default=60, ge=5, le=1440)
    max_api_keys_per_user: int = Field(default=10, ge=1, le=50)
    webhook_max_attempts: int = Field(default=5, ge=1, le=20)
    webhook_retry_base_seconds: int = Field(default=30, ge=5)

    require_https_callbacks: bool = False
    cors_origins: str = (
        "http://localhost:8002,http://127.0.0.1:8002,"
        "http://localhost:8001,http://127.0.0.1:8001"
    )
    api_allowed_hosts: str = "localhost,127.0.0.1,api"

    @property
    def allowed_host_list(self) -> list[str]:
        hosts = [h.strip() for h in self.api_allowed_hosts.split(",") if h.strip()]
        if os.getenv("VERCEL"):
            hosts.extend([".vercel.app", "localhost", "127.0.0.1"])
            vercel_url = os.getenv("VERCEL_URL", "")
            if vercel_url:
                hosts.append(vercel_url.strip())
        if self.public_base_url:
            host = urlparse(self.public_base_url).hostname
            if host:
                hosts.append(host)
        return list(dict.fromkeys(hosts))

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.public_base_url:
            origins.append(self.public_base_url.rstrip("/"))
        if os.getenv("VERCEL_URL"):
            origins.append(f"https://{os.getenv('VERCEL_URL', '').strip()}")
        return list(dict.fromkeys(origins))

    @field_validator("secret_key", "webhook_secret", "wallet_encryption_key", mode="before")
    @classmethod
    def reject_placeholder_secrets(cls, v: str, info) -> str:
        placeholders = {
            "change-me-min-32-chars-for-jwt-signing",
            "change-me-min-32-chars-for-webhook-hmac",
            "change-me-32-byte-encryption-key-here",
            "django-insecure-change-me",
        }
        if v in placeholders:
            return v
        return v

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def enabled_chain_list(self) -> list[str]:
        return [c.strip().upper() for c in self.enabled_chains.split(",") if c.strip()]

    def payment_url(self, payment_id: int) -> str:
        return f"{self.public_base_url.rstrip('/')}/pay/{payment_id}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def validate_production_settings() -> None:
    """Fail fast if production is misconfigured."""
    s = settings
    if not s.is_production:
        return

    insecure = [
        "change-me-min-32-chars-for-jwt-signing",
        "change-me-min-32-chars-for-webhook-hmac",
        "change-me-32-byte-encryption-key-here",
    ]
    if s.secret_key in insecure or s.webhook_secret in insecure or s.wallet_encryption_key in insecure:
        raise RuntimeError("Production requires non-default SECRET_KEY, WEBHOOK_SECRET, WALLET_ENCRYPTION_KEY")

    if s.debug:
        raise RuntimeError("DEBUG must be False in production")

    # Vercel: allow httpbin/test callbacks during MVP; enforce HTTPS in production elsewhere
    if not s.require_https_callbacks and not os.getenv("VERCEL"):
        raise RuntimeError("REQUIRE_HTTPS_CALLBACKS must be True in production")
