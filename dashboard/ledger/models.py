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
    # Gaxtron's own gateway fee for this platform (operator-set in the admin; the platform cannot change it).
    fee_bps = models.PositiveIntegerField(null=True, blank=True, validators=[MaxValueValidator(10000)])
    # The platform's own commission on each sale (platform-set via the API, capped by MAX_COMMISSION_BPS),
    # credited to `commission_recipient`, or to a "platform:revenue" user created on first use.
    commission_bps = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(10000)])
    commission_recipient = models.ForeignKey("EndUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
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

    end_user = models.ForeignKey(EndUser, on_delete=models.CASCADE, related_name="deposit_addresses")
    # Set for a per-order payment address; empty for the user's standing wallet address (one per user).
    payment = models.OneToOneField("Payment", null=True, blank=True, on_delete=models.PROTECT, related_name="deposit_address")
    address = models.CharField(max_length=40, unique=True)
    private_key_encrypted = models.TextField()
    last_scanned_ms = models.BigIntegerField(default=0)
    next_scan_at = models.DateTimeField(default=timezone.now, db_index=True)
    hot_until = models.DateTimeField(default=timezone.now)
    # USDT base units (6 decimals). Only credited-and-not-yet-swept funds are ever swept, so uncredited
    # dust or mistaken transfers stay put for an operator to decide on.
    credited_units = models.BigIntegerField(default=0)
    swept_units = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["end_user"], condition=Q(payment__isnull=True), name="one_standing_address_per_user"
            ),
        ]

    def __str__(self):
        return self.address


class Sweep(models.Model):
    """Moves credited USDT from a deposit address into the treasury. It changes no user balance — only where
    custody sits — so a failed sweep is harmless and simply retried."""

    class Status(models.TextChoices):
        FUNDING = "funding"  # treasury is sending TRX so the address can pay the transfer fee
        SWEEPING = "sweeping"  # USDT transfer to the treasury
        COMPLETED = "completed"
        FAILED = "failed"

    deposit = models.ForeignKey(DepositAddress, on_delete=models.PROTECT, related_name="sweeps")
    units = models.BigIntegerField()
    status = models.CharField(max_length=12, choices=Status.choices, db_index=True)
    fund_tx_id = models.CharField(max_length=64, blank=True, default="")
    fund_expiration_ms = models.BigIntegerField(null=True, blank=True)
    sweep_tx_id = models.CharField(max_length=64, blank=True, default="")
    sweep_expiration_ms = models.BigIntegerField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["deposit"], condition=Q(status__in=["funding", "sweeping"]), name="one_active_sweep_per_address"
            ),
        ]


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
    fee = models.DecimalField(default=0, **AMOUNT)  # Gaxtron's gateway fee
    commission = models.DecimalField(default=0, **AMOUNT)  # the platform's commission
    commission_recipient = models.ForeignKey(
        EndUser, null=True, blank=True, on_delete=models.PROTECT, related_name="escrows_as_commission_recipient"
    )
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

    @property
    def net_to_seller(self):
        return self.amount - self.fee - self.commission


def new_payment_id():
    return f"pay_{secrets.token_hex(12)}"


class Payment(models.Model):
    """A pay-from-any-wallet checkout for one order: the buyer sends USDT to a dedicated address, and once the
    amount has arrived (irreversibly) it is credited to the buyer and moved straight into escrow."""

    class Status(models.TextChoices):
        AWAITING_PAYMENT = "awaiting_payment"
        FUNDED = "funded"
        EXPIRED = "expired"

    public_id = models.CharField(max_length=40, unique=True, default=new_payment_id)
    platform = models.ForeignKey(GaxtronUser, on_delete=models.CASCADE, related_name="ledger_payments")
    reference = models.CharField(max_length=128)
    buyer = models.ForeignKey(EndUser, on_delete=models.PROTECT, related_name="payments_as_buyer")
    seller = models.ForeignKey(EndUser, on_delete=models.PROTECT, related_name="payments_as_seller")
    amount = models.DecimalField(**AMOUNT)
    commission_bps = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AWAITING_PAYMENT, db_index=True)
    escrow = models.OneToOneField(Escrow, null=True, blank=True, on_delete=models.PROTECT, related_name="payment")
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    funded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["platform", "reference"], name="uniq_payment_platform_reference"),
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
