"""Ledger, escrow and withdrawal state machines.

Invariants (each has a test, and `manage.py ledger_reconcile` re-checks them on live data):
  * every LedgerTransaction's entries sum to zero; all Account balances sum to zero
  * a non-EXTERNAL account balance never goes negative (checked under row locks + a DB constraint)
  * ledger rows are append-only
  * every money movement goes through post(); every request is scoped to one platform
"""
import hashlib
import json
import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from . import events, tron
from .models import CURRENCY, Account, EndUser, Entry, Escrow, LedgerTransaction, PlatformConfig, Withdrawal
from .serializers import EscrowSerializer, WithdrawalSerializer

QUANT = Decimal("0.000001")
MAX_AMOUNT = Decimal("1000000000")
Kind = Account.Kind
TxnKind = LedgerTransaction.Kind


class LedgerError(Exception):
    code = "ledger_error"
    http_status = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class InvalidRequest(LedgerError):
    code = "invalid_request"


class NotFound(LedgerError):
    code = "not_found"
    http_status = 404


class InsufficientFunds(LedgerError):
    code = "insufficient_funds"
    http_status = 402


class InvalidState(LedgerError):
    code = "invalid_state"
    http_status = 409


class Conflict(LedgerError):
    code = "conflict"
    http_status = 409


class Unavailable(LedgerError):
    code = "unavailable"
    http_status = 503


class LimitExceeded(LedgerError):
    code = "limit_exceeded"
    http_status = 422


def parse_amount(value, field="amount") -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise InvalidRequest(f"{field} must be a decimal number")
    if not amount.is_finite() or amount <= 0 or amount > MAX_AMOUNT:
        raise InvalidRequest(f"{field} must be greater than 0 and at most {MAX_AMOUNT}")
    if amount != amount.quantize(QUANT):
        raise InvalidRequest(f"{field} supports at most 6 decimal places")
    return amount.quantize(QUANT)


def fingerprint(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------- users & accounts


def get_or_create_end_user(platform, external_id, email=""):
    external_id = str(external_id).strip()
    if not external_id or len(external_id) > 128:
        raise InvalidRequest("user id must be 1-128 characters")
    return EndUser.objects.get_or_create(platform=platform, external_id=external_id, defaults={"email": email or ""})


def get_end_user(platform, external_id) -> EndUser:
    user = EndUser.objects.filter(platform=platform, external_id=str(external_id)).first()
    if not user:
        raise NotFound("User not found")
    return user


def _user_account(platform, end_user) -> Account:
    if end_user.platform_id != platform.id:
        raise RuntimeError("cross-tenant account access")
    account, _ = Account.objects.get_or_create(
        platform=platform, kind=Kind.USER, end_user=end_user, currency=CURRENCY
    )
    return account


def _system_account(platform, kind) -> Account:
    account, _ = Account.objects.get_or_create(platform=platform, kind=kind, end_user=None, currency=CURRENCY)
    return account


def _existing(platform, key, request_hash):
    txn = LedgerTransaction.objects.filter(platform=platform, idempotency_key=key).first()
    if txn and request_hash and txn.request_hash and txn.request_hash != request_hash:
        raise Conflict("Idempotency-Key was already used with different parameters")
    return txn


def post(platform, kind, legs, *, reference="", idempotency_key=None, request_hash="", description=""):
    """The only place balances change. legs = [(Account, signed Decimal)], must sum to zero.
    Returns (LedgerTransaction, replayed)."""
    if idempotency_key:
        existing = _existing(platform, idempotency_key, request_hash)
        if existing:
            return existing, True
    legs = [(account, amount) for account, amount in legs if amount != 0]
    if not legs or sum(amount for _, amount in legs) != 0:
        raise RuntimeError("unbalanced ledger transaction")
    if any(account.platform_id != platform.id for account, _ in legs):
        raise RuntimeError("cross-tenant ledger leg")
    try:
        with transaction.atomic():
            locked = {
                row.id: row
                for row in Account.objects.select_for_update()
                .filter(id__in=[account.id for account, _ in legs])
                .order_by("id")
            }
            txn = LedgerTransaction.objects.create(
                platform=platform, kind=kind, reference=reference, idempotency_key=idempotency_key,
                request_hash=request_hash, description=description[:255],
            )
            for account, amount in legs:
                row = locked[account.id]
                row.balance += amount
                if row.balance < 0 and row.kind != Kind.EXTERNAL:
                    raise InsufficientFunds("Insufficient available balance")
                Entry.objects.create(transaction=txn, account=row, amount=amount)
            for row in locked.values():
                row.save(update_fields=["balance"])
    except IntegrityError:
        existing = _existing(platform, idempotency_key, request_hash) if idempotency_key else None
        if existing:
            return existing, True
        raise
    return txn, False


# ---------------------------------------------------------------- balances


def balance_summary(platform, end_user) -> dict:
    account = Account.objects.filter(platform=platform, kind=Kind.USER, end_user=end_user).first()
    open_states = [Escrow.Status.HELD, Escrow.Status.DISPUTED]
    active_wd = [Withdrawal.Status.PENDING_APPROVAL, Withdrawal.Status.APPROVED, Withdrawal.Status.BROADCAST]

    def total(qs):
        return qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    return {
        "currency": CURRENCY,
        "available": account.balance if account else Decimal("0"),
        "held_as_buyer": total(Escrow.objects.filter(platform=platform, buyer=end_user, status__in=open_states)),
        "incoming_as_seller": total(Escrow.objects.filter(platform=platform, seller=end_user, status__in=open_states)),
        "pending_withdrawals": total(Withdrawal.objects.filter(platform=platform, end_user=end_user, status__in=active_wd)),
    }


# ---------------------------------------------------------------- deposits, sandbox, transfers


@transaction.atomic
def credit_deposit(platform, end_user, amount, tx_id, index=0):
    """Called by the chain watcher once a deposit is irreversible. Idempotent per (tx_id, index)."""
    amount = parse_amount(amount)
    txn, replayed = post(
        platform, TxnKind.DEPOSIT,
        [(_system_account(platform, Kind.EXTERNAL), -amount), (_user_account(platform, end_user), amount)],
        reference=tx_id, idempotency_key=f"deposit:{tx_id.lower()}:{index}", description="On-chain deposit",
    )
    if not replayed:
        events.emit(platform, "deposit.credited", {"user": end_user.external_id, "amount": str(amount), "tx_id": tx_id})
    return txn, replayed


def sandbox_credit(platform, end_user, amount, idempotency_key=None):
    if not settings.ENABLE_SANDBOX_CREDIT:
        raise NotFound("Not found")
    key = idempotency_key or uuid.uuid4().hex
    return credit_deposit(platform, end_user, amount, f"sandbox:{key}")


@transaction.atomic
def transfer(platform, from_user, to_user, amount, description="", idempotency_key=None):
    amount = parse_amount(amount)
    if from_user.id == to_user.id:
        raise InvalidRequest("from_user and to_user must be different")
    txn, replayed = post(
        platform, TxnKind.TRANSFER,
        [(_user_account(platform, from_user), -amount), (_user_account(platform, to_user), amount)],
        reference=f"{from_user.external_id}->{to_user.external_id}", description=description,
        idempotency_key=f"transfer:{idempotency_key}" if idempotency_key else None,
        request_hash=fingerprint(from_user.id, to_user.id, amount) if idempotency_key else "",
    )
    if not replayed:
        events.emit(platform, "transfer.created", {
            "id": txn.id, "from_user": from_user.external_id, "to_user": to_user.external_id, "amount": str(amount),
        })
    return txn, replayed


# ---------------------------------------------------------------- escrow


def compute_fee(platform, amount: Decimal) -> Decimal:
    config = PlatformConfig.objects.filter(platform=platform).first()
    bps = config.fee_bps if config and config.fee_bps is not None else settings.ESCROW_FEE_BPS
    if not 0 <= bps <= 10000:
        raise RuntimeError("fee_bps out of range")
    return (amount * bps / Decimal(10000)).quantize(QUANT, ROUND_HALF_UP)


def _emit_escrow(escrow, event_type):
    events.emit(escrow.platform, event_type, EscrowSerializer(escrow).data)


def _locked_escrow(platform, escrow_id) -> Escrow:
    escrow = (
        Escrow.objects.select_for_update(of=("self",))
        .select_related("buyer", "seller", "platform")
        .filter(platform=platform, public_id=escrow_id)
        .first()
    )
    if not escrow:
        raise NotFound("Escrow not found")
    return escrow


@transaction.atomic
def hold_escrow(platform, *, buyer, seller, amount, reference, metadata=None):
    """Moves `amount` from the buyer's available balance into escrow. Idempotent per reference."""
    amount = parse_amount(amount)
    reference = str(reference).strip()
    if not reference or len(reference) > 128:
        raise InvalidRequest("reference must be 1-128 characters")
    if buyer.id == seller.id:
        raise InvalidRequest("buyer and seller must be different users")

    existing = Escrow.objects.select_related("buyer", "seller").filter(platform=platform, reference=reference).first()
    if existing:
        if (existing.buyer_id, existing.seller_id, existing.amount) == (buyer.id, seller.id, amount):
            return existing, True
        raise Conflict("An escrow with this reference already exists with different details")

    try:
        with transaction.atomic():
            escrow = Escrow.objects.create(
                platform=platform, reference=reference, buyer=buyer, seller=seller, amount=amount,
                fee=compute_fee(platform, amount), metadata=metadata or {},
            )
    except IntegrityError:
        existing = Escrow.objects.select_related("buyer", "seller").get(platform=platform, reference=reference)
        if (existing.buyer_id, existing.seller_id, existing.amount) == (buyer.id, seller.id, amount):
            return existing, True
        raise Conflict("An escrow with this reference already exists with different details")

    post(
        platform, TxnKind.ESCROW_HOLD,
        [(_user_account(platform, buyer), -amount), (_system_account(platform, Kind.ESCROW), amount)],
        reference=escrow.public_id, idempotency_key=f"escrow:{escrow.public_id}:hold",
        description=f"Escrow hold for {reference}",
    )
    _emit_escrow(escrow, "escrow.created")
    return escrow, False


@transaction.atomic
def release_escrow(platform, escrow_id):
    """Pays the seller (minus the platform fee). Terminal; replaying returns the same result."""
    escrow = _locked_escrow(platform, escrow_id)
    if escrow.status == Escrow.Status.RELEASED:
        return escrow, True
    if escrow.status == Escrow.Status.REFUNDED:
        raise InvalidState("Escrow was already refunded")
    legs = [
        (_system_account(platform, Kind.ESCROW), -escrow.amount),
        (_user_account(platform, escrow.seller), escrow.amount - escrow.fee),
        (_system_account(platform, Kind.FEE), escrow.fee),
    ]
    post(
        platform, TxnKind.ESCROW_RELEASE, legs, reference=escrow.public_id,
        idempotency_key=f"escrow:{escrow.public_id}:release", description=f"Escrow release for {escrow.reference}",
    )
    escrow.status = Escrow.Status.RELEASED
    escrow.resolved_at = timezone.now()
    escrow.save(update_fields=["status", "resolved_at"])
    _emit_escrow(escrow, "escrow.released")
    return escrow, False


@transaction.atomic
def refund_escrow(platform, escrow_id):
    """Returns the full amount to the buyer (no fee). Terminal; replaying returns the same result."""
    escrow = _locked_escrow(platform, escrow_id)
    if escrow.status == Escrow.Status.REFUNDED:
        return escrow, True
    if escrow.status == Escrow.Status.RELEASED:
        raise InvalidState("Escrow was already released")
    post(
        platform, TxnKind.ESCROW_REFUND,
        [(_system_account(platform, Kind.ESCROW), -escrow.amount), (_user_account(platform, escrow.buyer), escrow.amount)],
        reference=escrow.public_id, idempotency_key=f"escrow:{escrow.public_id}:refund",
        description=f"Escrow refund for {escrow.reference}",
    )
    escrow.status = Escrow.Status.REFUNDED
    escrow.resolved_at = timezone.now()
    escrow.save(update_fields=["status", "resolved_at"])
    _emit_escrow(escrow, "escrow.refunded")
    return escrow, False


@transaction.atomic
def dispute_escrow(platform, escrow_id, reason):
    escrow = _locked_escrow(platform, escrow_id)
    if escrow.status == Escrow.Status.DISPUTED:
        return escrow, True
    if escrow.status != Escrow.Status.HELD:
        raise InvalidState(f"A {escrow.status} escrow cannot be disputed")
    escrow.status = Escrow.Status.DISPUTED
    escrow.dispute_reason = reason
    escrow.save(update_fields=["status", "dispute_reason"])
    _emit_escrow(escrow, "escrow.disputed")
    return escrow, False


# ---------------------------------------------------------------- withdrawals

_ACTIVE_WD = (Withdrawal.Status.PENDING_APPROVAL, Withdrawal.Status.APPROVED, Withdrawal.Status.BROADCAST)
_COUNTED_WD = _ACTIVE_WD + (Withdrawal.Status.COMPLETED,)


def _withdrawn_last_day(**scope) -> Decimal:
    since = timezone.now() - timedelta(hours=24)
    total = Withdrawal.objects.filter(created_at__gte=since, status__in=_COUNTED_WD, **scope).aggregate(t=Sum("amount"))
    return total["t"] or Decimal("0")


def _lock_withdrawal(withdrawal_id, platform=None) -> Withdrawal:
    qs = Withdrawal.objects.select_for_update(of=("self",)).select_related("end_user", "platform")
    if platform is not None:
        qs = qs.filter(platform=platform)
    withdrawal = qs.filter(public_id=withdrawal_id).first()
    if not withdrawal:
        raise NotFound("Withdrawal not found")
    return withdrawal


def _emit_withdrawal(withdrawal, event_type):
    events.emit(withdrawal.platform, event_type, WithdrawalSerializer(withdrawal).data)


@transaction.atomic
def request_withdrawal(platform, end_user, amount, destination, idempotency_key=None):
    amount = parse_amount(amount)
    destination = str(destination).strip()
    if not tron.is_valid_address(destination) or destination == tron.BURN_ADDRESS:
        raise InvalidRequest("destination must be a valid TRON (TRC-20) address")
    request_hash = fingerprint(end_user.id, amount, destination)
    if idempotency_key:
        existing = Withdrawal.objects.select_related("end_user", "platform").filter(
            platform=platform, idempotency_key=idempotency_key
        ).first()
        if existing:
            if existing.request_hash != request_hash:
                raise Conflict("Idempotency-Key was already used with different parameters")
            return existing, True

    fee = settings.WITHDRAWAL_FEE
    if amount < settings.WITHDRAWAL_MIN:
        raise InvalidRequest(f"Minimum withdrawal is {settings.WITHDRAWAL_MIN} {CURRENCY}")
    if amount <= fee:
        raise InvalidRequest("amount must be greater than the withdrawal fee")

    user_account = _user_account(platform, end_user)
    hold_account = _system_account(platform, Kind.WITHDRAWAL)
    # Serialize every withdrawal request of this platform so the daily caps cannot be raced.
    list(Account.objects.select_for_update().filter(id__in=[user_account.id, hold_account.id]).order_by("id"))
    if _withdrawn_last_day(end_user=end_user) + amount > settings.WITHDRAWAL_USER_DAILY_LIMIT:
        raise LimitExceeded("Daily withdrawal limit for this user exceeded")
    if _withdrawn_last_day(platform=platform) + amount > settings.WITHDRAWAL_PLATFORM_DAILY_LIMIT:
        raise LimitExceeded("Daily withdrawal limit for this platform exceeded")

    auto = amount <= settings.WITHDRAWAL_AUTO_APPROVE_MAX
    withdrawal = Withdrawal.objects.create(
        platform=platform, end_user=end_user, amount=amount, fee=fee, destination=destination,
        status=Withdrawal.Status.APPROVED if auto else Withdrawal.Status.PENDING_APPROVAL,
        approved_by="auto" if auto else "", approved_at=timezone.now() if auto else None,
        idempotency_key=idempotency_key, request_hash=request_hash,
    )
    post(
        platform, TxnKind.WITHDRAWAL, [(user_account, -amount), (hold_account, amount)],
        reference=withdrawal.public_id, idempotency_key=f"withdrawal:{withdrawal.public_id}:reserve",
        description="Withdrawal reserved",
    )
    _emit_withdrawal(withdrawal, "withdrawal.created")
    return withdrawal, False


def _reverse(withdrawal, new_status, reason):
    post(
        withdrawal.platform, TxnKind.WITHDRAWAL_REVERSAL,
        [
            (_system_account(withdrawal.platform, Kind.WITHDRAWAL), -withdrawal.amount),
            (_user_account(withdrawal.platform, withdrawal.end_user), withdrawal.amount),
        ],
        reference=withdrawal.public_id, idempotency_key=f"withdrawal:{withdrawal.public_id}:reverse",
        description=f"Withdrawal {new_status}",
    )
    withdrawal.status = new_status
    withdrawal.failure_reason = reason[:255]
    withdrawal.save(update_fields=["status", "failure_reason", "updated_at"])
    _emit_withdrawal(withdrawal, f"withdrawal.{new_status}")


@transaction.atomic
def approve_withdrawal(withdrawal_id, approver: str):
    """Operator action (admin). Never exposed on the platform API."""
    withdrawal = _lock_withdrawal(withdrawal_id)
    if withdrawal.status == Withdrawal.Status.APPROVED:
        return withdrawal
    if withdrawal.status != Withdrawal.Status.PENDING_APPROVAL:
        raise InvalidState(f"A {withdrawal.status} withdrawal cannot be approved")
    withdrawal.status = Withdrawal.Status.APPROVED
    withdrawal.approved_by = approver[:100]
    withdrawal.approved_at = timezone.now()
    withdrawal.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return withdrawal


@transaction.atomic
def mark_withdrawal_broadcast(withdrawal_id, tx_hash: str, expiration_ms=None):
    """Sender records the signed transaction id BEFORE broadcasting it (so a crash can be reconciled)."""
    withdrawal = _lock_withdrawal(withdrawal_id)
    if withdrawal.status == Withdrawal.Status.BROADCAST and withdrawal.tx_hash == tx_hash:
        return withdrawal
    if withdrawal.status != Withdrawal.Status.APPROVED:
        raise InvalidState(f"A {withdrawal.status} withdrawal cannot be broadcast")
    withdrawal.status = Withdrawal.Status.BROADCAST
    withdrawal.tx_hash = tx_hash
    withdrawal.tx_expiration_ms = expiration_ms
    withdrawal.save(update_fields=["status", "tx_hash", "tx_expiration_ms", "updated_at"])
    return withdrawal


@transaction.atomic
def complete_withdrawal(withdrawal_id):
    """Called only once the chain reports the transfer irreversibly successful."""
    withdrawal = _lock_withdrawal(withdrawal_id)
    if withdrawal.status == Withdrawal.Status.COMPLETED:
        return withdrawal
    if withdrawal.status != Withdrawal.Status.BROADCAST:
        raise InvalidState(f"A {withdrawal.status} withdrawal cannot be completed")
    legs = [
        (_system_account(withdrawal.platform, Kind.WITHDRAWAL), -withdrawal.amount),
        (_system_account(withdrawal.platform, Kind.EXTERNAL), withdrawal.net_amount),
        (_system_account(withdrawal.platform, Kind.FEE), withdrawal.fee),
    ]
    post(
        withdrawal.platform, TxnKind.WITHDRAWAL_COMPLETE, legs, reference=withdrawal.public_id,
        idempotency_key=f"withdrawal:{withdrawal.public_id}:complete", description="Withdrawal completed",
    )
    withdrawal.status = Withdrawal.Status.COMPLETED
    withdrawal.save(update_fields=["status", "updated_at"])
    _emit_withdrawal(withdrawal, "withdrawal.completed")
    return withdrawal


@transaction.atomic
def fail_withdrawal(withdrawal_id, reason, *, chain_confirmed_failure=False):
    """Refunds the user. A BROADCAST transfer may still confirm, so it can only be failed once the
    chain itself has confirmed it failed — otherwise the user would be paid twice."""
    withdrawal = _lock_withdrawal(withdrawal_id)
    if withdrawal.status == Withdrawal.Status.FAILED:
        return withdrawal
    if withdrawal.status == Withdrawal.Status.BROADCAST and not chain_confirmed_failure:
        raise InvalidState("A broadcast withdrawal can only fail after the chain confirms the transfer failed")
    if withdrawal.status not in (
        Withdrawal.Status.PENDING_APPROVAL, Withdrawal.Status.APPROVED, Withdrawal.Status.BROADCAST
    ):
        raise InvalidState(f"A {withdrawal.status} withdrawal cannot be failed")
    _reverse(withdrawal, Withdrawal.Status.FAILED, reason)
    return withdrawal


@transaction.atomic
def cancel_withdrawal(platform, withdrawal_id):
    withdrawal = _lock_withdrawal(withdrawal_id, platform)
    if withdrawal.status == Withdrawal.Status.CANCELLED:
        return withdrawal
    if withdrawal.status not in (Withdrawal.Status.PENDING_APPROVAL, Withdrawal.Status.APPROVED):
        raise InvalidState(f"A {withdrawal.status} withdrawal can no longer be cancelled")
    _reverse(withdrawal, Withdrawal.Status.CANCELLED, "Cancelled by platform")
    return withdrawal


# ---------------------------------------------------------------- reconciliation


def reconcile() -> list[str]:
    """Returns human-readable problems; empty means the books are consistent."""
    problems = []
    for row in Entry.objects.values("transaction_id").annotate(total=Sum("amount")).exclude(total=0):
        problems.append(f"transaction {row['transaction_id']} entries sum to {row['total']}, not 0")
    for account in Account.objects.annotate(entries_total=Sum("entries__amount")):
        if (account.entries_total or Decimal("0")) != account.balance:
            problems.append(f"account {account.id} balance {account.balance} != entries {account.entries_total}")
        if account.balance < 0 and account.kind != Kind.EXTERNAL:
            problems.append(f"account {account.id} ({account.kind}) is negative: {account.balance}")
    for platform_id in Account.objects.values_list("platform_id", flat=True).distinct():
        accounts = Account.objects.filter(platform_id=platform_id)
        if (accounts.aggregate(t=Sum("balance"))["t"] or 0) != 0:
            problems.append(f"platform {platform_id}: account balances do not sum to 0")
        open_escrow = Escrow.objects.filter(
            platform_id=platform_id, status__in=[Escrow.Status.HELD, Escrow.Status.DISPUTED]
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        held = accounts.filter(kind=Kind.ESCROW).aggregate(t=Sum("balance"))["t"] or Decimal("0")
        if open_escrow != held:
            problems.append(f"platform {platform_id}: escrow account {held} != open escrows {open_escrow}")
        active = Withdrawal.objects.filter(platform_id=platform_id, status__in=_ACTIVE_WD).aggregate(t=Sum("amount"))["t"] or Decimal("0")
        reserved = accounts.filter(kind=Kind.WITHDRAWAL).aggregate(t=Sum("balance"))["t"] or Decimal("0")
        if active != reserved:
            problems.append(f"platform {platform_id}: withdrawal hold {reserved} != active withdrawals {active}")
    return problems
