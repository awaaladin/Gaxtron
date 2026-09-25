import hashlib
import time
from decimal import Decimal as D

from django.test import TestCase, override_settings
from eth_keys import keys

from merchants import security

from . import chain, services, tron, tron_tx
from .models import DepositAddress, Withdrawal
from .tests import DEST, funded, make_platform, user
from .tron_client import TronAPIError

CONTRACT = "TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf"
OTHER_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
TREASURY_KEY = "11" * 32
TREASURY = tron_tx.Signer(TREASURY_KEY).address
USDT = dict(USDT_TRC20_CONTRACT=CONTRACT, TRON_TREASURY_PRIVATE_KEY=TREASURY_KEY)


def _v(n):
    out = b""
    while True:
        byte, n = n & 0x7F, n >> 7
        out += bytes([byte | (0x80 if n else 0)])
        if not n:
            return out


def _vi(field, n):
    return _v(field << 3) + _v(n)


def _ld(field, data):
    return _v((field << 3) | 2) + _v(len(data)) + data


def raw_tx(*, owner=TREASURY, contract=CONTRACT, recipient=DEST, units=5_000_000, fee_limit=100_000_000,
           expiration=None, call_value=0, contracts=1, extra_raw=b"", data=None):
    expiration = expiration if expiration is not None else int(time.time() * 1000) + 60_000
    data = data if data is not None else tron_tx.transfer_call_data(recipient, units)
    trigger = _ld(1, tron.address_to_bytes(owner)) + _ld(2, tron.address_to_bytes(contract))
    trigger += _vi(3, call_value) if call_value else b""
    trigger += _ld(4, data)
    param = _ld(1, b"type.googleapis.com/protocol.TriggerSmartContract") + _ld(2, trigger)
    contract_msg = _vi(1, 31) + _ld(2, param)
    raw = _ld(1, b"\x12\x34") + _ld(4, b"\x00" * 8) + _vi(8, expiration) + _ld(11, contract_msg) * contracts
    raw += _vi(14, int(time.time() * 1000)) + _vi(18, fee_limit) + extra_raw
    return {"txID": hashlib.sha256(raw).hexdigest(), "raw_data": {}, "raw_data_hex": raw.hex()}


def verify(tx, **overrides):
    args = dict(owner=TREASURY, contract=CONTRACT, recipient=DEST, units=5_000_000, fee_limit_max=100_000_000,
                now_ms=int(time.time() * 1000))
    args.update(overrides)
    return tron_tx.verify_trc20_transfer(tx["raw_data_hex"], tx["txID"], **args)


class FakeClient:
    def __init__(self):
        self.transfers, self.broadcasts, self.built = [], [], []
        self.info, self.full, self.tamper, self.fail = {}, {}, None, False

    def trc20_transfers_to(self, address, min_timestamp_ms):
        if self.fail:
            raise TronAPIError("down")
        return [t for t in self.transfers if t["to"] == address and t["block_timestamp"] >= min_timestamp_ms]

    def build_trc20_transfer(self, owner, contract, parameter_hex, fee_limit):
        recipient_bytes = bytes.fromhex(parameter_hex)[12:32]
        units = int.from_bytes(bytes.fromhex(parameter_hex)[32:64], "big")
        recipient = tron.bytes_to_address(b"\x41" + recipient_bytes)
        kwargs = dict(owner=owner, contract=contract, recipient=recipient, units=units, fee_limit=fee_limit)
        kwargs.update(self.tamper or {})
        tx = raw_tx(**kwargs)
        self.built.append(tx)
        return tx

    def broadcast(self, signed):
        self.broadcasts.append(signed)
        return {"result": True}

    def solidified_transaction_info(self, tx_id):
        return self.info.get(tx_id, {})

    def transaction_on_full_node(self, tx_id):
        return self.full.get(tx_id, {})


def transfer(to, units, tx_id, ts=1_000, contract=CONTRACT, kind="Transfer", decimals=6):
    return {"transaction_id": tx_id, "block_timestamp": ts, "from": DEST, "to": to, "type": kind, "value": str(units),
            "token_info": {"address": contract, "decimals": decimals, "symbol": "USDT"}}


TX1, TX2, TX3 = ("a" * 63 + "1", "b" * 63 + "2", "c" * 63 + "3")


@override_settings(**USDT)
class DepositTests(TestCase):
    def setUp(self):
        self.p, _ = make_platform()
        self.alice = user(self.p, "alice")
        self.client = FakeClient()

    def test_deposit_address_is_valid_unique_and_key_matches(self):
        deposit = chain.get_deposit_address(self.alice, create=True)
        self.assertTrue(tron.is_valid_address(deposit.address))
        self.assertEqual(chain.get_deposit_address(self.alice, create=True).pk, deposit.pk)
        self.assertIsNone(chain.get_deposit_address(user(self.p, "bob")))
        key = security.decrypt_private_key(deposit.private_key_encrypted)
        self.assertEqual(tron_tx.Signer(key).address, deposit.address)
        self.assertNotIn(key, repr(tron_tx.Signer(key)))

    def test_only_real_irreversible_usdt_deposits_are_credited(self):
        deposit = chain.get_deposit_address(self.alice, create=True)
        a = deposit.address
        self.client.transfers = [
            transfer(a, 25_000_000, TX1),
            transfer(a, 10_000_000, TX2, contract=OTHER_CONTRACT),  # look-alike token
            transfer(DEST, 10_000_000, TX2),  # someone else's address
            transfer(a, 500_000, TX3),  # below the dust minimum
            transfer(a, 10_000_000, TX3, kind="Approval"),
            transfer(a, 10_000_000, "short"),
            transfer(a, 10_000_000, TX2, decimals=18),
        ]
        self.assertEqual(chain.scan_due_deposits(self.client)["deposits_credited"], 1)
        self.assertEqual(services.balance_summary(self.p, self.alice)["available"], D("25"))
        self.assertEqual(services.reconcile(), [])

    def test_rescanning_never_double_credits_and_same_tx_pays_are_distinct(self):
        deposit = chain.get_deposit_address(self.alice, create=True)
        self.client.transfers = [transfer(deposit.address, 5_000_000, TX1), transfer(deposit.address, 7_000_000, TX1)]
        chain.scan_deposit(self.client, DepositAddress.objects.select_related("end_user__platform").get(pk=deposit.pk))
        for _ in range(3):
            chain.scan_deposit(self.client, DepositAddress.objects.select_related("end_user__platform").get(pk=deposit.pk))
        self.assertEqual(services.balance_summary(self.p, self.alice)["available"], D("12"))

    def test_api_outage_backs_off_instead_of_crashing(self):
        chain.get_deposit_address(self.alice, create=True)
        self.client.fail = True
        self.assertEqual(chain.scan_due_deposits(self.client)["deposit_addresses_scanned"], 0)
        self.assertEqual(chain.scan_due_deposits(self.client)["deposit_addresses_scanned"], 0)


class VerifierTests(TestCase):
    def test_accepts_the_exact_expected_transfer(self):
        self.assertGreater(verify(raw_tx()), int(time.time() * 1000))

    def test_rejects_every_kind_of_tampering(self):
        attacker = tron.address_from_evm_hex("0x" + "ab" * 20)
        cases = {
            "other recipient": raw_tx(recipient=attacker),
            "more money": raw_tx(units=5_000_001),
            "other token": raw_tx(contract=OTHER_CONTRACT),
            "other owner": raw_tx(owner=attacker),
            "call value": raw_tx(call_value=1),
            "two contracts": raw_tx(contracts=2),
            "huge fee limit": raw_tx(fee_limit=10**12),
            "no fee limit": raw_tx(fee_limit=0),
            "expired": raw_tx(expiration=1),
            "unknown raw field": raw_tx(extra_raw=_ld(9, b"x")),
            "wrong selector": raw_tx(data=b"\x23\xb8\x72\xdd" + tron_tx.transfer_call_data(DEST, 5_000_000)[4:]),
        }
        for name, tx in cases.items():
            with self.assertRaises(tron_tx.TxVerificationError, msg=name):
                verify(tx)

    def test_rejects_txid_that_does_not_match_the_bytes(self):
        tx = raw_tx()
        tx["txID"] = "0" * 64
        with self.assertRaises(tron_tx.TxVerificationError):
            verify(tx)
        with self.assertRaises(tron_tx.TxVerificationError):
            tron_tx.verify_trc20_transfer("zz", "0" * 64, owner=TREASURY, contract=CONTRACT, recipient=DEST,
                                          units=1, fee_limit_max=1, now_ms=0)

    def test_signature_recovers_to_the_treasury_key(self):
        signer = tron_tx.Signer(TREASURY_KEY)
        tx_id = hashlib.sha256(b"payload").hexdigest()
        signature = keys.Signature(bytes.fromhex(signer.sign(tx_id)))
        recovered = signature.recover_public_key_from_msg_hash(bytes.fromhex(tx_id))
        self.assertEqual(tron.address_from_evm_hex(recovered.to_checksum_address()), signer.address)


@override_settings(**USDT)
class SenderTests(TestCase):
    def setUp(self):
        self.p, _ = make_platform()
        self.alice = funded(self.p, "alice", "100")
        self.client = FakeClient()

    def approved_withdrawal(self, amount="20"):
        wd, _ = services.request_withdrawal(self.p, self.alice, amount, DEST)
        services.approve_withdrawal(wd.public_id, "operator")
        return wd

    @override_settings(TRON_TREASURY_PRIVATE_KEY="")
    def test_sender_is_disabled_without_a_treasury_key(self):
        wd = self.approved_withdrawal()
        self.assertTrue(chain.send_approved_withdrawals(self.client)["sender_disabled"])
        self.assertEqual(Withdrawal.objects.get(pk=wd.pk).status, Withdrawal.Status.APPROVED)

    def test_only_operator_approved_withdrawals_are_sent(self):
        services.request_withdrawal(self.p, self.alice, "20", DEST)
        self.assertEqual(chain.send_approved_withdrawals(self.client)["withdrawals_sent"], 0)
        self.assertEqual(self.client.built, [])

    def test_happy_path_records_txid_before_and_signs_correctly(self):
        wd = self.approved_withdrawal()
        self.assertEqual(chain.send_approved_withdrawals(self.client)["withdrawals_sent"], 1)
        wd.refresh_from_db()
        self.assertEqual(wd.status, Withdrawal.Status.BROADCAST)
        self.assertEqual(wd.tx_hash, self.client.built[0]["txID"])
        self.assertEqual(len(self.client.broadcasts), 1)
        sig = keys.Signature(bytes.fromhex(self.client.broadcasts[0]["signature"][0]))
        pub = sig.recover_public_key_from_msg_hash(bytes.fromhex(wd.tx_hash))
        self.assertEqual(tron.address_from_evm_hex(pub.to_checksum_address()), TREASURY)
        self.assertEqual(chain.send_approved_withdrawals(self.client)["withdrawals_sent"], 0)  # never re-sent
        self.assertEqual(len(self.client.broadcasts), 1)

    def test_a_tampered_api_response_is_never_signed_or_broadcast(self):
        attacker = tron.address_from_evm_hex("0x" + "ab" * 20)
        for tamper in ({"recipient": attacker}, {"units": 10**9}, {"contract": OTHER_CONTRACT}):
            wd = self.approved_withdrawal("10")
            self.client.tamper = tamper
            self.assertEqual(chain.send_approved_withdrawals(self.client)["withdrawals_sent"], 0)
            self.assertEqual(self.client.broadcasts, [])
            self.assertEqual(Withdrawal.objects.get(pk=wd.pk).status, Withdrawal.Status.APPROVED)
            services.fail_withdrawal(wd.public_id, "cleanup")

    def test_monitor_completes_on_success_and_books_balance(self):
        wd = self.approved_withdrawal()
        chain.send_approved_withdrawals(self.client)
        wd.refresh_from_db()
        self.assertEqual(chain.monitor_broadcast_withdrawals(self.client)["withdrawals_completed"], 0)
        self.client.info[wd.tx_hash] = {"receipt": {"result": "SUCCESS"}}
        self.assertEqual(chain.monitor_broadcast_withdrawals(self.client)["withdrawals_completed"], 1)
        self.assertEqual(Withdrawal.objects.get(pk=wd.pk).status, Withdrawal.Status.COMPLETED)
        self.assertEqual(services.reconcile(), [])

    def test_monitor_refunds_only_on_chain_proof_of_failure(self):
        wd = self.approved_withdrawal()
        chain.send_approved_withdrawals(self.client)
        wd.refresh_from_db()
        self.client.info[wd.tx_hash] = {"receipt": {"result": "OUT_OF_ENERGY"}}
        chain.monitor_broadcast_withdrawals(self.client)
        self.assertEqual(Withdrawal.objects.get(pk=wd.pk).status, Withdrawal.Status.FAILED)
        self.assertEqual(services.balance_summary(self.p, self.alice)["available"], D("100"))
        self.assertEqual(services.reconcile(), [])

    def test_expired_and_absent_is_refunded_but_present_or_unexpired_is_not(self):
        wd = self.approved_withdrawal()
        chain.send_approved_withdrawals(self.client)
        wd.refresh_from_db()
        chain.monitor_broadcast_withdrawals(self.client)  # not expired yet
        self.assertEqual(Withdrawal.objects.get(pk=wd.pk).status, Withdrawal.Status.BROADCAST)
        Withdrawal.objects.filter(pk=wd.pk).update(tx_expiration_ms=1)
        self.client.full[wd.tx_hash] = {"txID": wd.tx_hash}  # seen by the network: keep waiting
        chain.monitor_broadcast_withdrawals(self.client)
        self.assertEqual(Withdrawal.objects.get(pk=wd.pk).status, Withdrawal.Status.BROADCAST)
        self.client.full.clear()  # gone and expired: can never confirm
        chain.monitor_broadcast_withdrawals(self.client)
        self.assertEqual(Withdrawal.objects.get(pk=wd.pk).status, Withdrawal.Status.FAILED)
        self.assertEqual(services.reconcile(), [])
