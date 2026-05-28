from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, HttpUrl, field_validator

MAX_PAYMENT_AMOUNT = Decimal("1000000")


class CreatePaymentRequest(BaseModel):
    """Sepolia ETH payment — amount + merchant webhook only."""

    amount: Decimal = Field(gt=0, max_digits=36, decimal_places=18)
    callback_url: HttpUrl
    idempotency_key: str | None = Field(
        default=None, min_length=8, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$"
    )

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: Decimal) -> Decimal:
        if v > MAX_PAYMENT_AMOUNT:
            raise ValueError(f"Amount cannot exceed {MAX_PAYMENT_AMOUNT}")
        return v


class CreatePaymentResponse(BaseModel):
    payment_id: int
    payment_token: str
    payment_url: str
    wallet_address: str
    amount: Decimal
    currency: str = "ETH"
    chain: str = "ETH"
    status: str
    callback_url: str
    tx_hash: str | None = None
    confirmations: int = 0
    created_at: datetime
    expires_at: datetime | None = None


class PaymentResponse(BaseModel):
    id: int
    amount: Decimal
    chain: str
    currency: str
    status: str
    wallet_address: str
    callback_url: str
    tx_hash: str | None
    confirmations: int = 0
    payment_url: str | None = None
    created_at: datetime
    confirmed_at: datetime | None
    expires_at: datetime | None = None

    model_config = {"from_attributes": True}


class PublicPaymentStatus(BaseModel):
    """Public checkout polling — no secrets."""

    id: int
    public_token: str | None = None
    amount: Decimal
    currency: str
    chain: str
    status: str
    wallet_address: str
    address: str | None = None  # alias for wallet/QR clients
    tx_hash: str | None
    confirmations: int
    required_confirmations: int
    network: str
    created_at: datetime
    confirmed_at: datetime | None
    expires_at: datetime | None = None

    model_config = {"from_attributes": True}


class VerifyPaymentResponse(BaseModel):
    id: int
    status: str
    amount: Decimal
    chain: str
    currency: str
    wallet_address: str
    tx_hash: str | None
    confirmations: int = 0
    payment_url: str | None = None
    confirmed_at: datetime | None
    expires_at: datetime | None = None

    model_config = {"from_attributes": True}
