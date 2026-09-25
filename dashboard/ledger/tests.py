import hmac
from decimal import Decimal as D
from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from merchants import security
from merchants.models import ApiKey, GaxtronUser

from . import events, services, tron
from .models import Account, Entry, Escrow, LedgerImmutableError, Withdrawal

DEST = tron.address_from_evm_hex("0x11fE68cd67D2FEde7f326Fd6BC9Ee5F433ECBe9e")


def make_platform(name="acme"):
    user = GaxtronUser.objects.create_user(email=f"{name}@example.com", username=name, password="unused-pw")
    raw = security.generate_api_key()
    ApiKey.objects.create(user=user, key_hash=security.hash_api_key(raw), key_prefix=raw[:12])
    return user, raw


def user(platform, external_id):
    return services.get_or_create_end_user(platform, external_id)[0]


def funded(platform, external_id, amount):
    end_user = user(platform, external_id)
    services.credit_deposit(platform, end_user, amount, f"tx-{platform.id}-{external_id}-{amount}")
    return end_user


def available(platform, end_user):
    return services.balance_summary(platform, end_user)["available"]


class TronAddressTests(TestCase):
    def test_validation(self):
        self.assertTrue(tron.is_valid_address("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"))
        self.assertFalse(tron.is_valid_address("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6u"))
        self.assertFalse(tron.is_valid_address("0x11fE68cd67D2FEde7f326Fd6BC9Ee5F433ECBe9e"))
        self.assertFalse(tron.is_valid_address(""))
        self.assertEqual(tron.address_from_evm_hex("0x" + "00" * 20), tron.BURN_ADDRESS)
        self.assertTrue(tron.is_valid_address(DEST))


class LedgerServiceTests(TestCase):
    def setUp(self):
        self.p, _ = make_platform()

    def assertBooksBalance(self):
        self.assertEqual(services.reconcile(), [])

    def test_deposit_is_idempotent(self):
        alice = user(self.p, "alice")
        services.credit_deposit(self.p, alice, "25", "tx1")
        _, replayed = services.credit_deposit(self.p, alice, "25", "TX1")
        self.assertTrue(replayed)
        self.assertEqual(available(self.p, alice), D("25"))
        self.assertBooksBalance()

    def test_amounts_are_validated(self):
        alice = user(self.p, "alice")
        for bad in ["0", "-1", "abc", "NaN", "1.0000001", "9999999999999"]:
            with self.assertRaises(services.InvalidRequest, msg=bad):
                services.credit_deposit(self.p, alice, bad, "tx-bad")

    @override_settings(ESCROW_FEE_BPS=250)
    def test_hold_and_release_pays_seller_minus_fee(self):
        buyer, seller = funded(self.p, "buyer", "100"), user(self.p, "seller")
        escrow, _ = services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="100", reference="o1")
        self.assertEqual(available(self.p, buyer), D("0"))
        self.assertEqual(services.balance_summary(self.p, seller)["incoming_as_seller"], D("100"))
        services.release_escrow(self.p, escrow.public_id)
        self.assertEqual(available(self.p, seller), D("97.5"))
        fee_account = Account.objects.get(platform=self.p, kind=Account.Kind.FEE)
        self.assertEqual(fee_account.balance, D("2.5"))
        self.assertBooksBalance()

    def test_refund_returns_full_amount(self):
        buyer, seller = funded(self.p, "buyer", "60"), user(self.p, "seller")
        escrow, _ = services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="60", reference="o1")
        services.refund_escrow(self.p, escrow.public_id)
        self.assertEqual(available(self.p, buyer), D("60"))
        self.assertBooksBalance()

    def test_release_is_idempotent_and_terminal(self):
        buyer, seller = funded(self.p, "buyer", "50"), user(self.p, "seller")
        escrow, _ = services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="50", reference="o1")
        services.release_escrow(self.p, escrow.public_id)
        _, replayed = services.release_escrow(self.p, escrow.public_id)
        self.assertTrue(replayed)
        self.assertEqual(available(self.p, seller), D("50"))
        with self.assertRaises(services.InvalidState):
            services.refund_escrow(self.p, escrow.public_id)
        self.assertBooksBalance()

    def test_insufficient_funds_leaves_no_trace(self):
        buyer, seller = funded(self.p, "buyer", "10"), user(self.p, "seller")
        with self.assertRaises(services.InsufficientFunds):
            services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="50", reference="o1")
        self.assertFalse(Escrow.objects.exists())
        self.assertEqual(available(self.p, buyer), D("10"))
        self.assertBooksBalance()

    def test_same_reference_replays_but_conflicting_details_are_rejected(self):
        buyer, seller = funded(self.p, "buyer", "100"), user(self.p, "seller")
        first, _ = services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="30", reference="o1")
        again, replayed = services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="30", reference="o1")
        self.assertTrue(replayed)
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(available(self.p, buyer), D("70"))
        with self.assertRaises(services.Conflict):
            services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="31", reference="o1")
        with self.assertRaises(services.InvalidRequest):
            services.hold_escrow(self.p, buyer=buyer, seller=buyer, amount="1", reference="o2")

    def test_dispute_then_resolve(self):
        buyer, seller = funded(self.p, "buyer", "20"), user(self.p, "seller")
        escrow, _ = services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="20", reference="o1")
        services.dispute_escrow(self.p, escrow.public_id, "item not received")
        with self.assertRaises(services.NotFound):
            services.dispute_escrow(self.p, "esc_missing", "x")
        services.refund_escrow(self.p, escrow.public_id)
        with self.assertRaises(services.InvalidState):
            services.dispute_escrow(self.p, escrow.public_id, "too late")
        self.assertBooksBalance()

    def test_transfer_idempotency_detects_mismatched_reuse(self):
        alice, bob = funded(self.p, "alice", "100"), user(self.p, "bob")
        services.transfer(self.p, alice, bob, "10", idempotency_key="k1")
        _, replayed = services.transfer(self.p, alice, bob, "10", idempotency_key="k1")
        self.assertTrue(replayed)
        self.assertEqual(available(self.p, bob), D("10"))
        with self.assertRaises(services.Conflict):
            services.transfer(self.p, alice, bob, "11", idempotency_key="k1")
        with self.assertRaises(services.InsufficientFunds):
            services.transfer(self.p, alice, bob, "1000")
        self.assertBooksBalance()

    @override_settings(WITHDRAWAL_FEE=D("1"))
    def test_withdrawal_lifecycle(self):
        alice = funded(self.p, "alice", "100")
        wd, _ = services.request_withdrawal(self.p, alice, "20", DEST)
        self.assertEqual(wd.status, Withdrawal.Status.PENDING_APPROVAL)
        self.assertEqual(available(self.p, alice), D("80"))
        self.assertEqual(wd.net_amount, D("19"))
        with self.assertRaises(services.InvalidState):
            services.mark_withdrawal_broadcast(wd.public_id, "txid")
        services.approve_withdrawal(wd.public_id, "operator")
        services.mark_withdrawal_broadcast(wd.public_id, "txid")
        services.complete_withdrawal(wd.public_id)
        self.assertEqual(Account.objects.get(platform=self.p, kind=Account.Kind.FEE).balance, D("1"))
        self.assertEqual(Account.objects.get(platform=self.p, kind=Account.Kind.EXTERNAL).balance, D("-81"))
        self.assertBooksBalance()

    def test_withdrawal_destination_and_minimum_are_enforced(self):
        alice = funded(self.p, "alice", "100")
        for bad in ["0x11fE68cd67D2FEde7f326Fd6BC9Ee5F433ECBe9e", tron.BURN_ADDRESS, "T-nope", ""]:
            with self.assertRaises(services.InvalidRequest, msg=bad):
                services.request_withdrawal(self.p, alice, "10", bad)
        with self.assertRaises(services.InvalidRequest):
            services.request_withdrawal(self.p, alice, "0.5", DEST)
        self.assertEqual(available(self.p, alice), D("100"))

    def test_cancel_restores_balance_and_broadcast_cannot_fail_without_chain_proof(self):
        alice = funded(self.p, "alice", "100")
        wd, _ = services.request_withdrawal(self.p, alice, "30", DEST)
        services.cancel_withdrawal(self.p, wd.public_id)
        self.assertEqual(available(self.p, alice), D("100"))

        wd2, _ = services.request_withdrawal(self.p, alice, "30", DEST)
        services.approve_withdrawal(wd2.public_id, "op")
        services.mark_withdrawal_broadcast(wd2.public_id, "txid2")
        with self.assertRaises(services.InvalidState):
            services.fail_withdrawal(wd2.public_id, "guessing")
        with self.assertRaises(services.InvalidState):
            services.cancel_withdrawal(self.p, wd2.public_id)
        services.fail_withdrawal(wd2.public_id, "reverted on chain", chain_confirmed_failure=True)
        self.assertEqual(available(self.p, alice), D("100"))
        self.assertBooksBalance()

    @override_settings(WITHDRAWAL_USER_DAILY_LIMIT=D("30"))
    def test_user_daily_limit(self):
        alice = funded(self.p, "alice", "100")
        services.request_withdrawal(self.p, alice, "20", DEST)
        with self.assertRaises(services.LimitExceeded):
            services.request_withdrawal(self.p, alice, "20", DEST)

    @override_settings(WITHDRAWAL_PLATFORM_DAILY_LIMIT=D("30"))
    def test_platform_daily_limit_caps_a_compromised_key(self):
        a, b = funded(self.p, "a", "100"), funded(self.p, "b", "100")
        services.request_withdrawal(self.p, a, "20", DEST)
        with self.assertRaises(services.LimitExceeded):
            services.request_withdrawal(self.p, b, "20", DEST)

    @override_settings(WITHDRAWAL_AUTO_APPROVE_MAX=D("50"))
    def test_auto_approval_only_below_threshold(self):
        alice = funded(self.p, "alice", "500")
        small, _ = services.request_withdrawal(self.p, alice, "40", DEST)
        big, _ = services.request_withdrawal(self.p, alice, "60", DEST)
        self.assertEqual(small.status, Withdrawal.Status.APPROVED)
        self.assertEqual(big.status, Withdrawal.Status.PENDING_APPROVAL)

    def test_withdrawal_idempotency_key(self):
        alice = funded(self.p, "alice", "100")
        wd, _ = services.request_withdrawal(self.p, alice, "10", DEST, idempotency_key="w1")
        again, replayed = services.request_withdrawal(self.p, alice, "10", DEST, idempotency_key="w1")
        self.assertTrue(replayed)
        self.assertEqual(wd.pk, again.pk)
        self.assertEqual(available(self.p, alice), D("90"))
        with self.assertRaises(services.Conflict):
            services.request_withdrawal(self.p, alice, "11", DEST, idempotency_key="w1")

    def test_ledger_history_is_append_only(self):
        funded(self.p, "alice", "10")
        entry = Entry.objects.first()
        with self.assertRaises(LedgerImmutableError):
            entry.save()
        with self.assertRaises(LedgerImmutableError):
            entry.delete()
        with self.assertRaises(LedgerImmutableError):
            Entry.objects.all().update(amount=D("999"))

    def test_reconcile_detects_tampered_balance(self):
        alice = funded(self.p, "alice", "10")
        self.assertBooksBalance()
        Account.objects.filter(end_user=alice).update(balance=D("999"))
        self.assertTrue(services.reconcile())

    def test_platforms_are_fully_isolated(self):
        other, _ = make_platform("other")
        a_buyer, a_seller = funded(self.p, "u1", "100"), user(self.p, "u2")
        funded(other, "u1", "5")
        escrow, _ = services.hold_escrow(self.p, buyer=a_buyer, seller=a_seller, amount="40", reference="o1")
        self.assertEqual(available(other, user(other, "u1")), D("5"))
        with self.assertRaises(services.NotFound):
            services.release_escrow(other, escrow.public_id)
        with self.assertRaises(services.NotFound):
            services.get_end_user(other, "u2")
        wd, _ = services.request_withdrawal(self.p, a_buyer, "10", DEST)
        with self.assertRaises(services.NotFound):
            services.cancel_withdrawal(other, wd.public_id)
        with self.assertRaises(RuntimeError):
            services.transfer(other, user(other, "u1"), a_seller, "1")
        self.assertBooksBalance()


@override_settings(ENABLE_SANDBOX_CREDIT=True)
class LedgerApiTests(TestCase):
    def setUp(self):
        self.p, self.key = make_platform()
        limiter = mock.patch("ledger.views.check_rate_limit", return_value=True)
        limiter.start()
        self.addCleanup(limiter.stop)
        self.c = APIClient()
        self.c.credentials(HTTP_X_API_KEY=self.key)

    def test_requires_a_valid_api_key(self):
        anon = APIClient()
        r = anon.get("/v1/users/alice")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"]["code"], "unauthorized")
        bad = APIClient()
        bad.credentials(HTTP_X_API_KEY="gax_" + "x" * 43)
        self.assertEqual(bad.get("/v1/users/alice").status_code, 401)

    def test_escrow_flow(self):
        self.assertEqual(self.c.post("/v1/users", {"external_id": "alice"}, format="json").status_code, 201)
        credit = self.c.post("/v1/sandbox/credit", {"user": "alice", "amount": "100"}, format="json")
        self.assertEqual(credit.json()["available"], "100.000000")

        body = {"reference": "order-1", "buyer": "alice", "seller": "bob", "amount": "40"}
        created = self.c.post("/v1/escrows", body, format="json")
        self.assertEqual(created.status_code, 201)
        escrow_id = created.json()["id"]
        self.assertEqual(self.c.post("/v1/escrows", body, format="json").status_code, 200)

        released = self.c.post(f"/v1/escrows/{escrow_id}/release", format="json")
        self.assertEqual(released.json()["status"], "released")
        self.assertEqual(self.c.get("/v1/users/bob/balance").json()["available"], "40.000000")
        self.assertEqual(self.c.get("/v1/users/alice").json()["balance"]["available"], "60.000000")
        self.assertEqual(len(self.c.get("/v1/escrows?status=released").json()["data"]), 1)
        self.assertEqual(self.c.get("/v1/users/bob/transactions").json()["data"][0]["type"], "escrow_release")
        self.assertEqual(self.c.post(f"/v1/escrows/{escrow_id}/refund", format="json").status_code, 409)

    @override_settings(ENABLE_SANDBOX_CREDIT=False)
    def test_sandbox_credit_is_off_by_default(self):
        r = self.c.post("/v1/sandbox/credit", {"user": "alice", "amount": "100"}, format="json")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(Entry.objects.exists())

    def test_error_shapes(self):
        r = self.c.post("/v1/users", {}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "invalid_request")
        self.assertIn("external_id", r.json()["error"]["fields"])
        self.assertEqual(self.c.get("/v1/escrows/esc_nope").json()["error"]["code"], "not_found")
        self.c.post("/v1/sandbox/credit", {"user": "alice", "amount": "5"}, format="json")
        r = self.c.post("/v1/escrows", {"reference": "o", "buyer": "alice", "seller": "bob", "amount": "50"}, format="json")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (402, "insufficient_funds"))

    def test_rate_limit_and_idempotency_key_length(self):
        with mock.patch("ledger.views.check_rate_limit", return_value=False):
            r = self.c.get("/v1/users/alice")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (429, "rate_limited"))
        r = self.c.post("/v1/transfers", {"from_user": "a", "to_user": "b", "amount": "1"}, format="json",
                        HTTP_IDEMPOTENCY_KEY="k" * 200)
        self.assertEqual(r.status_code, 400)

    def test_transfer_idempotency_over_http(self):
        self.c.post("/v1/sandbox/credit", {"user": "alice", "amount": "100"}, format="json")
        send = {"from_user": "alice", "to_user": "bob", "amount": "10"}
        self.assertEqual(self.c.post("/v1/transfers", send, format="json", HTTP_IDEMPOTENCY_KEY="t1").status_code, 201)
        self.assertEqual(self.c.post("/v1/transfers", send, format="json", HTTP_IDEMPOTENCY_KEY="t1").status_code, 200)
        self.assertEqual(self.c.get("/v1/users/bob/balance").json()["available"], "10.000000")
        other = dict(send, amount="11")
        r = self.c.post("/v1/transfers", other, format="json", HTTP_IDEMPOTENCY_KEY="t1")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (409, "conflict"))

    def test_withdrawal_over_http(self):
        self.c.post("/v1/sandbox/credit", {"user": "alice", "amount": "100"}, format="json")
        bad = self.c.post("/v1/withdrawals", {"user": "alice", "amount": "10", "destination": "0xabc"}, format="json")
        self.assertEqual(bad.status_code, 400)
        r = self.c.post("/v1/withdrawals", {"user": "alice", "amount": "10", "destination": DEST}, format="json")
        self.assertEqual((r.status_code, r.json()["status"]), (201, "pending_approval"))
        cancelled = self.c.post(f"/v1/withdrawals/{r.json()['id']}/cancel", format="json")
        self.assertEqual(cancelled.json()["status"], "cancelled")

    def test_platforms_cannot_see_each_others_data(self):
        self.c.post("/v1/sandbox/credit", {"user": "alice", "amount": "100"}, format="json")
        self.c.post("/v1/escrows", {"reference": "o", "buyer": "alice", "seller": "bob", "amount": "10"}, format="json")
        escrow_id = self.c.get("/v1/escrows").json()["data"][0]["id"]
        _, other_key = make_platform("other")
        intruder = APIClient()
        intruder.credentials(HTTP_X_API_KEY=other_key)
        self.assertEqual(intruder.get(f"/v1/escrows/{escrow_id}").status_code, 404)
        self.assertEqual(intruder.post(f"/v1/escrows/{escrow_id}/release", format="json").status_code, 404)
        self.assertEqual(intruder.get("/v1/users/alice").status_code, 404)
        self.assertEqual(intruder.get("/v1/escrows").json()["data"], [])

    def test_webhook_url_is_ssrf_checked(self):
        r = self.c.put("/v1/webhook-config", {"url": "http://127.0.0.1/hook"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_signed_webhook_delivery_with_retry_backoff(self):
        with mock.patch("ledger.views.validate_callback_url"):
            cfg = self.c.put("/v1/webhook-config", {"url": "https://hooks.example.com/g"}, format="json").json()
        self.assertTrue(cfg["signing_secret"].startswith("whsec_"))
        self.c.post("/v1/sandbox/credit", {"user": "alice", "amount": "100"}, format="json")
        self.c.post("/v1/escrows", {"reference": "o", "buyer": "alice", "seller": "bob", "amount": "10"}, format="json")

        sent = []

        def ok(url, content=None, headers=None, **kwargs):
            sent.append((url, content, headers))
            return mock.Mock(status_code=200, text="ok")

        with mock.patch("ledger.events.validate_callback_url"), mock.patch("ledger.events.httpx.post", side_effect=ok):
            stats = events.deliver_pending()
        self.assertEqual(stats["platform_events_delivered"], 2)
        _, body, headers = sent[0]
        parts = dict(item.split("=", 1) for item in headers["X-Gaxtron-Signature"].split(","))
        expected = events.sign(cfg["signing_secret"], int(parts["t"]), body)
        self.assertTrue(hmac.compare_digest(parts["v1"], expected))
        self.assertEqual({headers["X-Gaxtron-Event"] for _, _, headers in sent}, {"deposit.credited", "escrow.created"})

        self.c.post("/v1/escrows", {"reference": "o2", "buyer": "alice", "seller": "bob", "amount": "5"}, format="json")
        boom = mock.Mock(status_code=500, text="down")
        with mock.patch("ledger.events.validate_callback_url"), mock.patch("ledger.events.httpx.post", return_value=boom):
            self.assertEqual(events.deliver_pending()["platform_events_attempted"], 1)
            self.assertEqual(events.deliver_pending()["platform_events_attempted"], 0)

    def test_rotating_the_secret_invalidates_the_old_one(self):
        old = self.c.get("/v1/webhook-config").json()["signing_secret"]
        new = self.c.post("/v1/webhook-config/rotate-secret", format="json").json()["signing_secret"]
        self.assertNotEqual(old, new)
        self.assertEqual(self.c.get("/v1/webhook-config").json()["signing_secret"], new)
