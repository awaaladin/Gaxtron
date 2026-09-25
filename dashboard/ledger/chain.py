"""TRON workers: deposit addresses + watcher, treasury sender, broadcast monitor.

Safety rules baked in:
  * deposits are credited only from *solidified* (irreversible) transfers of exactly our USDT contract
  * a withdrawal is signed only after tron_tx.verify_trc20_transfer() approves the exact bytes
  * the transaction id is persisted BEFORE broadcasting, and a broadcast withdrawal is completed or failed only on
    on-chain proof (irreversible result, or expiry with the transaction absent from the network)
"""
import logging
import time
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from eth_account import Account as EthAccount

from merchants import security

from . import services, tron, tron_tx
from .models import DepositAddress, Sweep, Withdrawal
from .tron_client import TronAPIError, TronClient

logger = logging.getLogger(__name__)

UNITS = Decimal(10**6)
OVERLAP_MS = 10 * 60 * 1000  # re-read recent history each scan; crediting is idempotent
HOT_INTERVAL = timedelta(seconds=20)
COLD_INTERVAL = timedelta(minutes=10)
HOT_WINDOW = timedelta(hours=2)
ERROR_BACKOFF = timedelta(minutes=1)
EXPIRY_GRACE_MS = 10 * 60 * 1000


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------- deposit addresses & watcher


def get_deposit_address(end_user, *, create=False):
    deposit = DepositAddress.objects.filter(end_user=end_user).first()
    if deposit is None:
        if not create:
            return None
        account = EthAccount.create()
        try:
            with transaction.atomic():
                deposit = DepositAddress.objects.create(
                    end_user=end_user,
                    address=tron.address_from_evm_hex(account.address),
                    private_key_encrypted=security.encrypt_private_key(account.key.hex()),
                )
        except IntegrityError:
            deposit = DepositAddress.objects.get(end_user=end_user)
    if create:
        now = timezone.now()
        DepositAddress.objects.filter(pk=deposit.pk).update(hot_until=now + HOT_WINDOW, next_scan_at=now)
    return deposit


def scan_deposit(client, deposit) -> int:
    """Credits new irreversible USDT deposits; returns how many were newly credited."""
    since = max(0, deposit.last_scanned_ms - OVERLAP_MS) if deposit.last_scanned_ms else 0
    ordinal, newest, credited = defaultdict(int), deposit.last_scanned_ms, 0
    for item in client.trc20_transfers_to(deposit.address, since):
        try:
            newest = max(newest, int(item.get("block_timestamp") or 0))
            token = item.get("token_info") or {}
            if item.get("type") != "Transfer" or item.get("to") != deposit.address:
                continue
            if token.get("address") != settings.USDT_TRC20_CONTRACT or int(token.get("decimals")) != 6:
                continue
            tx_id, units = str(item["transaction_id"]), int(item["value"])
            if len(tx_id) != 64 or units <= 0:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        index = ordinal[tx_id]
        ordinal[tx_id] += 1
        amount = Decimal(units) / UNITS
        if amount < settings.TRON_DEPOSIT_MIN:
            continue
        try:
            with transaction.atomic():  # the counter must move together with the ledger credit
                _, replayed = services.credit_deposit(deposit.end_user.platform, deposit.end_user, amount, tx_id, index)
                if not replayed:
                    DepositAddress.objects.filter(pk=deposit.pk).update(credited_units=F("credited_units") + units)
        except services.LedgerError:
            logger.exception("Deposit %s could not be credited", tx_id)
            continue
        credited += 0 if replayed else 1

    now = timezone.now()
    hot_until = now + timedelta(minutes=30) if credited else deposit.hot_until
    interval = HOT_INTERVAL if now < hot_until else COLD_INTERVAL
    DepositAddress.objects.filter(pk=deposit.pk).update(
        last_scanned_ms=newest, next_scan_at=now + interval, hot_until=hot_until
    )
    return credited


def scan_due_deposits(client=None, limit=20) -> dict:
    client = client or TronClient()
    due = DepositAddress.objects.filter(next_scan_at__lte=timezone.now()).select_related("end_user__platform")
    scanned = credited = 0
    for deposit in due.order_by("next_scan_at")[:limit]:
        try:
            credited += scan_deposit(client, deposit)
            scanned += 1
        except TronAPIError:
            logger.warning("Deposit scan failed for %s; backing off", deposit.address)
            DepositAddress.objects.filter(pk=deposit.pk).update(next_scan_at=timezone.now() + ERROR_BACKOFF)
    return {"deposit_addresses_scanned": scanned, "deposits_credited": credited}


# ---------------------------------------------------------------- withdrawals


def load_treasury():
    key = settings.TRON_TREASURY_PRIVATE_KEY.strip()
    if not key:
        return None
    if not settings.USDT_TRC20_CONTRACT:
        raise ImproperlyConfigured("USDT_TRC20_CONTRACT must be set to send withdrawals")
    signer = tron_tx.Signer(key)
    if settings.TRON_TREASURY_ADDRESS and settings.TRON_TREASURY_ADDRESS != signer.address:
        raise ImproperlyConfigured("TRON_TREASURY_ADDRESS does not match TRON_TREASURY_PRIVATE_KEY")
    return signer


def _send_one(client, signer, public_id) -> int:
    withdrawal = Withdrawal.objects.filter(public_id=public_id, status=Withdrawal.Status.APPROVED).first()
    if withdrawal is None:
        return 0
    contract = settings.USDT_TRC20_CONTRACT
    units = int(withdrawal.net_amount * UNITS)
    tx = client.build_trc20_transfer(
        signer.address, contract, tron_tx.transfer_parameter_hex(withdrawal.destination, units), settings.TRON_FEE_LIMIT_SUN
    )
    try:
        expiration = tron_tx.verify_trc20_transfer(
            tx["raw_data_hex"], tx["txID"], owner=signer.address, contract=contract,
            recipient=withdrawal.destination, units=units, fee_limit_max=settings.TRON_FEE_LIMIT_SUN, now_ms=_now_ms(),
        )
    except (KeyError, tron_tx.TxVerificationError):
        logger.error("SECURITY: refusing to sign a transaction that does not match withdrawal %s", public_id)
        raise
    signature = signer.sign(tx["txID"])
    # Persist the id first: if we crash before/while broadcasting, the monitor can still resolve it.
    services.mark_withdrawal_broadcast(withdrawal.public_id, tx["txID"], expiration)
    result = client.broadcast({
        "txID": tx["txID"], "raw_data": tx["raw_data"], "raw_data_hex": tx["raw_data_hex"],
        "visible": False, "signature": [signature],
    })
    if not result.get("result") and result.get("code") != "DUP_TRANSACTION":
        logger.error("Broadcast of %s was not accepted (%s); monitor will resolve it", public_id, result.get("code"))
    return 1


def send_approved_withdrawals(client=None, limit=5) -> dict:
    signer = load_treasury()
    if signer is None:
        return {"withdrawals_sent": 0, "sender_disabled": True}
    client = client or TronClient()
    sent = 0
    ids = list(Withdrawal.objects.filter(status=Withdrawal.Status.APPROVED).order_by("id").values_list("public_id", flat=True)[:limit])
    for public_id in ids:
        try:
            sent += _send_one(client, signer, public_id)
        except (TronAPIError, tron_tx.TxVerificationError, KeyError, services.LedgerError):
            logger.exception("Withdrawal %s was not sent this round", public_id)
    return {"withdrawals_sent": sent}


def monitor_broadcast_withdrawals(client=None) -> dict:
    client = client or TronClient()
    completed = failed = 0
    for withdrawal in Withdrawal.objects.filter(status=Withdrawal.Status.BROADCAST).order_by("id"):
        try:
            info = client.solidified_transaction_info(withdrawal.tx_hash)
            if info:
                result = (info.get("receipt") or {}).get("result")
                if result == "SUCCESS":
                    services.complete_withdrawal(withdrawal.public_id)
                    completed += 1
                else:
                    services.fail_withdrawal(
                        withdrawal.public_id, f"Transfer failed on-chain ({result or 'unknown'})",
                        chain_confirmed_failure=True,
                    )
                    failed += 1
            elif withdrawal.tx_expiration_ms and _now_ms() > withdrawal.tx_expiration_ms + EXPIRY_GRACE_MS:
                # Expired and the network has no record of it: it can never be included, so refunding is safe.
                if not client.transaction_on_full_node(withdrawal.tx_hash):
                    services.fail_withdrawal(
                        withdrawal.public_id, "Transaction expired before it was included",
                        chain_confirmed_failure=True,
                    )
                    failed += 1
        except (TronAPIError, services.LedgerError):
            logger.exception("Could not resolve withdrawal %s this round", withdrawal.public_id)
    return {"withdrawals_completed": completed, "withdrawals_failed": failed}


# ---------------------------------------------------------------- sweeping deposits into the treasury

_ACTIVE_SWEEP = (Sweep.Status.FUNDING, Sweep.Status.SWEEPING)


def _deposit_signer(deposit) -> tron_tx.Signer:
    signer = tron_tx.Signer(security.decrypt_private_key(deposit.private_key_encrypted))
    if signer.address != deposit.address:
        raise RuntimeError(f"stored key does not match deposit address {deposit.address}")
    return signer


def _expired_and_gone(client, tx_id, expiration_ms) -> bool:
    """True only when the transaction can never be included: past expiry (+grace) and unknown to the network."""
    return bool(
        expiration_ms and _now_ms() > expiration_ms + EXPIRY_GRACE_MS and not client.transaction_on_full_node(tx_id)
    )


def _record_and_broadcast(client, sweep, prefix, tx, expiration, signature):
    # Persist the id first: a crash between here and the broadcast is resolved by expiry, never by guessing.
    Sweep.objects.filter(pk=sweep.pk).update(**{f"{prefix}_tx_id": tx["txID"], f"{prefix}_expiration_ms": expiration})
    result = client.broadcast({
        "txID": tx["txID"], "raw_data": tx["raw_data"], "raw_data_hex": tx["raw_data_hex"],
        "visible": False, "signature": [signature],
    })
    if not result.get("result") and result.get("code") != "DUP_TRANSACTION":
        logger.error("Sweep %s %s broadcast not accepted (%s)", sweep.pk, prefix, result.get("code"))


def _fund_deposit_address(client, treasury, sweep) -> None:
    deposit = sweep.deposit
    top_up = max(settings.SWEEP_TRX_TARGET_SUN, settings.SWEEP_FEE_LIMIT_SUN) - client.trx_balance(deposit.address)
    if top_up <= 0:
        return
    if client.trx_balance(treasury.address) < top_up:
        logger.warning("Treasury has too little TRX to fund sweep fees (%s sun needed)", top_up)
        return
    tx = client.build_trx_transfer(treasury.address, deposit.address, top_up)
    expiration = tron_tx.verify_trx_transfer(
        tx["raw_data_hex"], tx["txID"], owner=treasury.address, recipient=deposit.address, sun=top_up, now_ms=_now_ms()
    )
    _record_and_broadcast(client, sweep, "fund", tx, expiration, treasury.sign(tx["txID"]))


def _send_sweep_transfer(client, treasury, sweep) -> None:
    deposit, contract = sweep.deposit, settings.USDT_TRC20_CONTRACT
    signer = _deposit_signer(deposit)
    tx = client.build_trc20_transfer(
        deposit.address, contract, tron_tx.transfer_parameter_hex(treasury.address, sweep.units), settings.SWEEP_FEE_LIMIT_SUN
    )
    try:
        expiration = tron_tx.verify_trc20_transfer(
            tx["raw_data_hex"], tx["txID"], owner=deposit.address, contract=contract, recipient=treasury.address,
            units=sweep.units, fee_limit_max=settings.SWEEP_FEE_LIMIT_SUN, now_ms=_now_ms(),
        )
    except (KeyError, tron_tx.TxVerificationError):
        logger.error("SECURITY: refusing to sign a sweep transaction that does not match sweep %s", sweep.pk)
        raise
    _record_and_broadcast(client, sweep, "sweep", tx, expiration, signer.sign(tx["txID"]))


def _fail_sweep(sweep, reason) -> None:
    Sweep.objects.filter(pk=sweep.pk, status__in=_ACTIVE_SWEEP).update(status=Sweep.Status.FAILED, failure_reason=reason[:255])


def _advance_sweep(client, treasury, sweep) -> None:
    deposit = sweep.deposit
    if sweep.status == Sweep.Status.FUNDING:
        if client.trx_balance(deposit.address) >= settings.SWEEP_FEE_LIMIT_SUN:
            Sweep.objects.filter(pk=sweep.pk, status=Sweep.Status.FUNDING).update(status=Sweep.Status.SWEEPING)
            sweep.status = Sweep.Status.SWEEPING
        elif not sweep.fund_tx_id:
            _fund_deposit_address(client, treasury, sweep)
            return
        elif _expired_and_gone(client, sweep.fund_tx_id, sweep.fund_expiration_ms):
            _fail_sweep(sweep, "TRX funding transaction expired")
            return
        else:
            return
    if sweep.status == Sweep.Status.SWEEPING:
        if not sweep.sweep_tx_id:
            _send_sweep_transfer(client, treasury, sweep)
            return
        info = client.solidified_transaction_info(sweep.sweep_tx_id)
        if info:
            if (info.get("receipt") or {}).get("result") == "SUCCESS":
                with transaction.atomic():
                    done = Sweep.objects.filter(pk=sweep.pk, status=Sweep.Status.SWEEPING).update(
                        status=Sweep.Status.COMPLETED
                    )
                    if done:
                        DepositAddress.objects.filter(pk=deposit.pk).update(swept_units=F("swept_units") + sweep.units)
            else:
                _fail_sweep(sweep, "Sweep transfer failed on-chain")
        elif _expired_and_gone(client, sweep.sweep_tx_id, sweep.sweep_expiration_ms):
            _fail_sweep(sweep, "Sweep transaction expired before it was included")


def sweep_deposits(client=None, limit=3) -> dict:
    treasury = load_treasury()
    if treasury is None:
        return {"sweeps_started": 0, "sweeper_disabled": True}
    client = client or TronClient()
    for sweep in Sweep.objects.filter(status__in=_ACTIVE_SWEEP).select_related("deposit").order_by("id"):
        try:
            _advance_sweep(client, treasury, sweep)
        except Exception:  # one bad sweep must never stop the others
            logger.exception("Sweep %s could not advance this round", sweep.pk)

    min_units = int(settings.SWEEP_MIN_USDT * UNITS)
    candidates = (
        DepositAddress.objects.annotate(pending=F("credited_units") - F("swept_units"))
        .filter(pending__gte=min_units).exclude(sweeps__status__in=_ACTIVE_SWEEP).order_by("-pending")[:limit]
    )
    started = 0
    for deposit in candidates:
        try:
            units = min(deposit.pending, client.trc20_balance(deposit.address, settings.USDT_TRC20_CONTRACT))
            if units < min_units:
                continue  # the chain shows less than the ledger credited; leave it for an operator
            funded = client.trx_balance(deposit.address) >= settings.SWEEP_FEE_LIMIT_SUN
            try:
                with transaction.atomic():
                    sweep = Sweep.objects.create(
                        deposit=deposit, units=units, status=Sweep.Status.SWEEPING if funded else Sweep.Status.FUNDING
                    )
            except IntegrityError:
                continue
            started += 1
            sweep.deposit = deposit
            _advance_sweep(client, treasury, sweep)
        except Exception:
            logger.exception("Could not start a sweep for %s", deposit.address)
    return {"sweeps_started": started}


def tick(client=None) -> dict:
    client = client or TronClient()
    stats = {}
    for step in (scan_due_deposits, send_approved_withdrawals, monitor_broadcast_withdrawals, sweep_deposits):
        try:
            stats.update(step(client))
        except Exception:
            logger.exception("Chain worker step %s failed", step.__name__)
    return stats
