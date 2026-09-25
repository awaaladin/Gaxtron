import hashlib
import time
from decimal import Decimal as D

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from eth_keys import keys

from . import chain, services, tron, tron_tx
from .models import DepositAddress, Sweep
from .tests import make_platform, user
from .test_chain import CONTRACT, TREASURY, TX1, USDT, FakeClient, _ld, _vi, raw_tx, transfer

ATTACKER = tron.address_from_evm_hex("0x" + "ab" * 20)
FEE_LIMIT = 40_000_000


def raw_trx_tx(*, owner, to, sun, expiration=None, fee_limit=0):
    expiration = expiration if expiration is not None else int(time.time() * 1000) + 60_000
    inner = _ld(1, tron.address_to_bytes(owner)) + _ld(2, tron.address_to_bytes(to)) + _vi(3, sun)
    param = _ld(1, b"type.googleapis.com/protocol.TransferContract") + _ld(2, inner)
    raw = _ld(1, b"\x12\x34") + _ld(4, b"\x00" * 8) + _vi(8, expiration) + _ld(11, _vi(1, 1) + _ld(2, param))
    raw += _vi(14, int(time.time() * 1000)) + (_vi(18, fee_limit) if fee_limit else b"")
    return {"txID": hashlib.sha256(raw).hexdigest(), "raw_data": {}, "raw_data_hex": raw.hex()}


class SweepClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.trx, self.usdt, self.trx_tamper, self.built_trx = {TREASURY: 10**10}, {}, None, []

    def trx_balance(self, address):
        return self.trx.get(address, 0)

    def trc20_balance(self, address, contract):
        return self.usdt.get(address, 0)

    def build_trx_transfer(self, owner, recipient, sun):
        kwargs = dict(owner=owner, to=recipient, sun=sun)
        kwargs.update(self.trx_tamper or {})
        tx = raw_trx_tx(**kwargs)
        self.built_trx.append(tx)
        return tx


def signer_of(signed_tx) -> str:
    sig = keys.Signature(bytes.fromhex(signed_tx["signature"][0]))
    pub = sig.recover_public_key_from_msg_hash(bytes.fromhex(signed_tx["txID"]))
    return tron.address_from_evm_hex(pub.to_checksum_address())


class TrxVerifierTests(TestCase):
    def check(self, tx, **overrides):
        args = dict(owner=TREASURY, recipient=ATTACKER, sun=5_000_000, now_ms=int(time.time() * 1000))
        args.update(overrides)
        return tron_tx.verify_trx_transfer(tx["raw_data_hex"], tx["txID"], **args)

    def test_accepts_exact_transfer_and_rejects_tampering(self):
        self.assertTrue(self.check(raw_trx_tx(owner=TREASURY, to=ATTACKER, sun=5_000_000)))
        bad = {
            "other recipient": raw_trx_tx(owner=TREASURY, to=TREASURY, sun=5_000_000),
            "other amount": raw_trx_tx(owner=TREASURY, to=ATTACKER, sun=5_000_001),
            "other owner": raw_trx_tx(owner=ATTACKER, to=ATTACKER, sun=5_000_000),
            "fee limit": raw_trx_tx(owner=TREASURY, to=ATTACKER, sun=5_000_000, fee_limit=1),
            "expired": raw_trx_tx(owner=TREASURY, to=ATTACKER, sun=5_000_000, expiration=1),
            "token call instead": raw_tx(),
        }
        for name, tx in bad.items():
            with self.assertRaises(tron_tx.TxVerificationError, msg=name):
                self.check(tx)


@override_settings(**USDT, SWEEP_MIN_USDT=D("20"), SWEEP_TRX_TARGET_SUN=FEE_LIMIT, SWEEP_FEE_LIMIT_SUN=FEE_LIMIT)
class SweeperTests(TestCase):
    def setUp(self):
        self.p, _ = make_platform()
        self.alice = user(self.p, "alice")
        self.client = SweepClient()
        self.deposit = chain.get_deposit_address(self.alice, create=True)

    def credit(self, usdt="25", onchain=None):
        units = int(D(usdt) * 10**6)
        self.client.transfers.append(transfer(self.deposit.address, units, TX1))
        chain.scan_due_deposits(self.client)
        self.client.usdt[self.deposit.address] = units if onchain is None else onchain
        self.deposit.refresh_from_db()

    def test_full_sweep_lifecycle_moves_custody_but_no_user_balance(self):
        self.credit("25")
        self.assertEqual(self.deposit.credited_units, 25_000_000)

        self.assertEqual(chain.sweep_deposits(self.client)["sweeps_started"], 1)
        sweep = Sweep.objects.get()
        self.assertEqual(sweep.status, Sweep.Status.FUNDING)
        self.assertEqual(len(self.client.broadcasts), 1)
        self.assertEqual(signer_of(self.client.broadcasts[0]), TREASURY)  # treasury paid the TRX top-up

        chain.sweep_deposits(self.client)  # TRX has not arrived: wait, do not fund twice
        self.assertEqual(len(self.client.broadcasts), 1)

        self.client.trx[self.deposit.address] = FEE_LIMIT
        chain.sweep_deposits(self.client)
        sweep.refresh_from_db()
        self.assertEqual(sweep.status, Sweep.Status.SWEEPING)
        self.assertEqual(len(self.client.broadcasts), 2)
        self.assertEqual(signer_of(self.client.broadcasts[1]), self.deposit.address)  # the deposit key signed it

        self.client.info[sweep.sweep_tx_id] = {"receipt": {"result": "SUCCESS"}}
        chain.sweep_deposits(self.client)
        sweep.refresh_from_db()
        self.deposit.refresh_from_db()
        self.assertEqual(sweep.status, Sweep.Status.COMPLETED)
        self.assertEqual(self.deposit.swept_units, 25_000_000)
        self.assertEqual(chain.sweep_deposits(self.client)["sweeps_started"], 0)
        self.assertEqual(services.balance_summary(self.p, self.alice)["available"], D("25"))
        self.assertEqual(services.reconcile(), [])

    def test_address_that_already_has_trx_is_not_funded_again(self):
        self.credit("25")
        self.client.trx[self.deposit.address] = FEE_LIMIT
        chain.sweep_deposits(self.client)
        self.assertEqual(self.client.built_trx, [])
        self.assertEqual(Sweep.objects.get().status, Sweep.Status.SWEEPING)
        self.assertEqual(len(self.client.broadcasts), 1)

    def test_only_credited_funds_are_swept(self):
        self.credit("25", onchain=30_000_000)  # 5 USDT arrived that the ledger never credited
        self.client.trx[self.deposit.address] = FEE_LIMIT
        chain.sweep_deposits(self.client)
        self.assertEqual(Sweep.objects.get().units, 25_000_000)

    def test_small_or_missing_balances_are_not_swept(self):
        self.credit("5")
        self.assertEqual(chain.sweep_deposits(self.client)["sweeps_started"], 0)
        self.client.transfers.append(transfer(self.deposit.address, 30_000_000, "d" * 64, ts=2_000))
        chain.scan_due_deposits(self.client)
        self.client.usdt[self.deposit.address] = 10_000_000  # chain shows less than credited: leave it alone
        self.assertEqual(chain.sweep_deposits(self.client)["sweeps_started"], 0)
        self.assertEqual(self.client.broadcasts, [])

    def test_tampered_sweep_transaction_is_never_broadcast_then_recovers(self):
        self.credit("25")
        self.client.trx[self.deposit.address] = FEE_LIMIT
        self.client.tamper = {"recipient": ATTACKER}
        chain.sweep_deposits(self.client)
        self.assertEqual(self.client.broadcasts, [])
        self.assertEqual(Sweep.objects.get().sweep_tx_id, "")
        self.client.tamper = None
        chain.sweep_deposits(self.client)
        self.assertEqual(len(self.client.broadcasts), 1)

    def test_tampered_funding_transaction_is_never_broadcast(self):
        self.credit("25")
        self.client.trx_tamper = {"to": ATTACKER}
        chain.sweep_deposits(self.client)
        self.assertEqual(self.client.broadcasts, [])
        self.assertEqual(Sweep.objects.get().fund_tx_id, "")

    def test_failed_sweep_changes_nothing_and_is_retried(self):
        self.credit("25")
        self.client.trx[self.deposit.address] = FEE_LIMIT
        chain.sweep_deposits(self.client)
        sweep = Sweep.objects.get()
        self.client.info[sweep.sweep_tx_id] = {"receipt": {"result": "REVERT"}}
        chain.sweep_deposits(self.client)
        self.deposit.refresh_from_db()
        self.assertEqual(Sweep.objects.get(pk=sweep.pk).status, Sweep.Status.FAILED)
        self.assertEqual(self.deposit.swept_units, 0)
        self.assertEqual(Sweep.objects.count(), 2)  # a fresh attempt started

    def test_expired_and_absent_transaction_fails_but_a_visible_one_keeps_waiting(self):
        self.credit("25")
        self.client.trx[self.deposit.address] = FEE_LIMIT
        chain.sweep_deposits(self.client)
        sweep = Sweep.objects.get()
        Sweep.objects.filter(pk=sweep.pk).update(sweep_expiration_ms=1)
        self.client.full[sweep.sweep_tx_id] = {"txID": sweep.sweep_tx_id}
        chain.sweep_deposits(self.client)
        self.assertEqual(Sweep.objects.get(pk=sweep.pk).status, Sweep.Status.SWEEPING)
        self.client.full.clear()
        chain.sweep_deposits(self.client)
        self.assertEqual(Sweep.objects.get(pk=sweep.pk).status, Sweep.Status.FAILED)

    def test_only_one_active_sweep_per_address(self):
        Sweep.objects.create(deposit=self.deposit, units=1, status=Sweep.Status.FUNDING)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Sweep.objects.create(deposit=self.deposit, units=1, status=Sweep.Status.SWEEPING)
        Sweep.objects.create(deposit=self.deposit, units=1, status=Sweep.Status.FAILED)  # history is unrestricted

    @override_settings(TRON_TREASURY_PRIVATE_KEY="")
    def test_disabled_without_a_treasury_key(self):
        self.credit("25")
        self.assertTrue(chain.sweep_deposits(self.client)["sweeper_disabled"])
        self.assertEqual(Sweep.objects.count(), 0)

    def test_a_deposit_key_that_does_not_match_its_address_is_refused(self):
        self.credit("25")
        other = chain.get_deposit_address(user(self.p, "bob"), create=True)
        DepositAddress.objects.filter(pk=self.deposit.pk).update(private_key_encrypted=other.private_key_encrypted)
        self.client.trx[self.deposit.address] = FEE_LIMIT
        chain.sweep_deposits(self.client)
        self.assertEqual(self.client.broadcasts, [])
