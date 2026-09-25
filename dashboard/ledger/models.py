"""Custodial USDT ledger + escrow for platforms (Choropia and any other integrator).

A "platform" is an existing merchants.GaxtronUser holding an API key. Money is double-entry:
every LedgerTransaction's entries sum to zero, and Account balances are a cache of their
entries, changed only under row locks by ledger.services.post().
"""
import secrets

from django.core.validators import MaxValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from merchants import security
from merchants.models import GaxtronUser

CURRENCY = "USDT"
AMOUNT = {"max_digits": 30, "decimal_places": 6}


class LedgerImmutableError(Exception):
    pass


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise LedgerImmutableError("ledger rows are append-only")

    def delete(self):
        raise LedgerImmutableError("ledger rows are append-only")


class AppendOnlyModel(models.Model):
    """Ledger history is never edited. Also enforced by a Postgres trigger (migration 0002),
    which additionally covers cascade deletes and raw SQL that bypass these Python guards."""

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise LedgerImmutableError("ledger rows are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerImmutableError("ledger rows are append-only")


def new_escrow_id():
    return f"esc_{secrets.token_hex(12)}"


def new_withdrawal_id():
    return f"wd_{secrets.token_hex(12)}"


def new_event_id():
    return f"evt_{secrets.token_hex(12)}"


def new_webhook_secret():
    return f"whsec_{secrets.token_hex(24)}"


def new_encrypted_webhook_secret():
    return security.encrypt_private_key(new_webhook_secret())


class PlatformConfig(models.Model):
    platform = models.OneToOneField(GaxtronUser, on_delete=models.CASCADE, related_name="ledger_config")
    webhook_url = models.TextField(blank=True, default="")
    webhook_secret_encrypted = models.CharField(max_length=255, default=new_encrypted_webhook_secret)
    fee_bps = models.PositiveIntegerField(null=True, blank=True, validators=[MaxValueValidator(10000)])
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def signing_secret(self) -> str:
        return security.decrypt_private_key(self.webhook_secret_encrypted)

    def rotate_secret(self) -> str:
        plain = new_webhook_secret()
        self.webhook_secret_encrypted = security.encrypt_private_key(plain)
        self.save(update_fields=["webhook_secret_encrypted"])
        return plain

    def __str__(self):
        return f"config:{self.platform_id}"


class EndUser(models.Model):
    platform = models.ForeignKey(GaxtronUser, on_delete=models.CASCADE, related_name="end_users")
    external_id = models.CharField(max_length=128)
    email = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["platform", "external_id"], name="uniq_enduser_platform_external"),
        ]

    def __str__(self):
        return f"{self.platform_id}:{self.external_id}"


class DepositAddress(models.Model):
    """One TRON address per user. The private key is Fernet-encrypted; it is only needed to sweep
    deposits into the treasury, never to credit them."""

    end_user = models.OneToOneField(EndUser, on_delete=models.CASCADE, related_name="deposit_address")
    address = models.CharField(max_length=40, unique=True)
    private_key_encrypted = models.TextField()
    last_scanned_ms = models.BigIntegerField(default=0)
    next_scan_at = models.DateTimeField(default=timezone.now, db_index=True)
    hot_until = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.address


class Account(models.Model):
    class Kind(models.TextChoices):
        USER = "user"
        ESCROW = "escrow"
        WITHDRAWAL = "withdrawal"
        FEE = "fee"
        EXTERNAL = "external"

    platform = models.ForeignKey(GaxtronUser, on_delete=models.CASCADE, related_name="ledger_accounts")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    end_user = models.ForeignKey(EndUser, on_delete=models.CASCADE, null=True, blank=True, related_name="accounts")
    currency = models.CharField(max_length=10, default=CURRENCY)
    balance = models.DecimalField(default=0, **AMOUNT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["end_user", "currency"], condition=Q(kind="user"), name="uniq_user_account"),
            models.UniqueConstraint(
                fields=["platform", "kind", "currency"], condition=~Q(kind="user"), name="uniq_system_account"
            ),
            models.CheckConstraint(
                condition=Q(kind="external") | Q(balance__gte=0), name="balance_nonneg_unless_external"
            ),
        ]

    def __str__(self):
        return f"{self.kind}:{self.platform_id}:{self.end_user_id}"


class LedgerTransaction(AppendOnlyModel):
    class Kind(models.TextChoices):
        DEPOSIT = "deposit"
        TRANSFER = "transfer"
        ESCROW_HOLD = "escrow_hold"
        ESCROW_RELEASE = "escrow_release"
        ESCROW_REFUND = "escrow_refund"
        WITHDRAWAL = "withdrawal"
        WITHDRAWAL_COMPLETE = "withdrawal_complete"
        WITHDRAWAL_REVERSAL = "withdrawal_reversal"

    platform = models.ForeignKey(GaxtronUser, on_delete=models.CASCADE, related_name="ledger_transactions")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    reference = models.CharField(max_length=128, blank=True, default="")
    idempotency_key = models.CharField(max_length=160, null=True, blank=True)
    request_hash = models.CharField(max_length=64, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="uniq_ledger_txn_idempotency",
            ),
        ]


class Entry(AppendOnlyModel):
    transaction = models.ForeignKey(LedgerTransaction, on_delete=models.CASCADE, related_name="entries")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="entries")
    amount = models.DecimalField(**AMOUNT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["account", "-id"], name="entry_account_recent")]


class Escrow(models.Model):
    class Status(models.TextChoices):
        HELD = "held"
        DISPUTED = "disputed"
        RELEASED = "released"
        REFUNDED = "refunded"

    public_id = models.CharField(max_length=40, unique=True, default=new_escrow_id)
    platform = models.ForeignKey(GaxtronUser, on_delete=models.CASCADE, related_name="escrows")
    reference = models.CharField(max_length=128)
    buyer = models.ForeignKey(EndUser, on_delete=models.PROTECT, related_name="escrows_as_buyer")
    seller = models.ForeignKey(EndUser, on_delete=models.PROTECT, related_name="escrows_as_seller")
    amount = models.DecimalField(**AMOUNT)
    fee = models.DecimalField(default=0, **AMOUNT)
    currency = models.CharField(max_length=10, default=CURRENCY)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.HELD, db_index=True)
    dispute_reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["platform", "reference"], name="uniq_escrow_platform_reference"),
        ]


class Withdrawal(models.Model):
    class Status(models.TextChoices):
        PENDING_APPROVAL = "pending_approval"
        APPROVED = "approved"
        BROADCAST = "broadcast"
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELLED = "cancelled"

    public_id = models.CharField(max_length=40, unique=True, default=new_withdrawal_id)
    platform = models.ForeignKey(GaxtronUser, on_delete=models.CASCADE, related_name="withdrawals")
    end_user = models.ForeignKey(EndUser, on_delete=models.PROTECT, related_name="withdrawals")
    amount = models.DecimalField(**AMOUNT)
    fee = models.DecimalField(default=0, **AMOUNT)
    currency = models.CharField(max_length=10, default=CURRENCY)
    destination = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Status.choices, db_index=True)
    tx_hash = models.CharField(max_length=128, blank=True, default="")
    tx_expiration_ms = models.BigIntegerField(null=True, blank=True)
    approved_by = models.CharField(max_length=100, blank=True, default="")
    approved_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=160, null=True, blank=True)
    request_hash = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="uniq_withdrawal_idempotency",
            ),
        ]

    @property
    def net_amount(self):
        return self.amount - self.fee


class WebhookEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        DELIVERED = "delivered"
        FAILED = "failed"

    event_id = models.CharField(max_length=40, unique=True, default=new_event_id)
    platform = models.ForeignKey(GaxtronUser, on_delete=models.CASCADE, related_name="webhook_events")
    type = models.CharField(max_length=48)
    payload = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    attempts = models.IntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    response_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_attempt_at"], name="webhook_due")]
