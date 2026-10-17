from decimal import Decimal as D
from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from . import chain, services
from .models import Account, Payment, PlatformConfig
from .test_chain import USDT, FakeClient, transfer
from .tests import available, funded, make_platform, user


@override_settings(ESCROW_FEE_BPS=250)  # Gaxtron's gateway fee: 2.5%
class FeeSplitTests(TestCase):
    def setUp(self):
        self.p, _ = make_platform()

    def test_gateway_fee_only_by_default(self):
        buyer, seller = funded(self.p, "buyer", "100"), user(self.p, "seller")
        escrow, _ = services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="100", reference="o1")
        self.assertEqual((escrow.fee, escrow.commission), (D("2.5"), D("0")))
        services.release_escrow(self.p, escrow.public_id)
        self.assertEqual(available(self.p, seller), D("97.5"))
        self.assertEqual(services.reconcile(), [])

    def test_platform_commission_is_paid_to_platform_revenue_by_default(self):
        config = PlatformConfig.objects.get_or_create(platform=self.p)[0]
        config.commission_bps = 1000  # 10%
        config.save(update_fields=["commission_bps"])
        buyer, seller = funded(self.p, "buyer", "100"), user(self.p, "seller")

        escrow, _ = services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="100", reference="o1")
        self.assertEqual((escrow.fee, escrow.commission), (D("2.5"), D("10")))
        services.release_escrow(self.p, escrow.public_id)

        self.assertEqual(available(self.p, seller), D("87.5"))
        revenue = services.platform_revenue_user(self.p)
        self.assertEqual(available(self.p, revenue), D("10"))
        self.assertEqual(Account.objects.get(platform=self.p, kind=Account.Kind.FEE).balance, D("2.5"))
        self.assertEqual(services.reconcile(), [])

    def test_commission_can_be_redirected_to_a_specific_user(self):
        payout = user(self.p, "choropia-treasury")
        config = PlatformConfig.objects.get_or_create(platform=self.p)[0]
        config.commission_bps, config.commission_recipient = 500, payout
        config.save(update_fields=["commission_bps", "commission_recipient"])
        buyer, seller = funded(self.p, "buyer", "40"), user(self.p, "seller")
        escrow, _ = services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="40", reference="o1")
        services.release_escrow(self.p, escrow.public_id)
        self.assertEqual(available(self.p, payout), D("2"))
        self.assertEqual(services.reconcile(), [])

    def test_per_escrow_commission_override(self):
        buyer, seller = funded(self.p, "buyer", "100"), user(self.p, "seller")
        escrow, _ = services.hold_escrow(
            self.p, buyer=buyer, seller=seller, amount="100", reference="o1", commission_bps=2000
        )
        self.assertEqual(escrow.commission, D("20"))

    def test_commission_over_cap_is_rejected(self):
        buyer, seller = funded(self.p, "buyer", "100"), user(self.p, "seller")
        with self.assertRaises(services.InvalidRequest):
            services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="100", reference="o1", commission_bps=5000)

    def test_refund_ignores_both_fees_buyer_gets_everything_back(self):
        config = PlatformConfig.objects.get_or_create(platform=self.p)[0]
        config.commission_bps = 1000
        config.save(update_fields=["commission_bps"])
        buyer, seller = funded(self.p, "buyer", "50"), user(self.p, "seller")
        escrow, _ = services.hold_escrow(self.p, buyer=buyer, seller=seller, amount="50", reference="o1")
        services.refund_escrow(self.p, escrow.public_id)
        self.assertEqual(available(self.p, buyer), D("50"))
        self.assertEqual(services.reconcile(), [])


@override_settings(**USDT)
class PaymentFlowTests(TestCase):
    def setUp(self):
        self.p, _ = make_platform()
        self.seller = user(self.p, "seller")
        self.client_ = FakeClient()

    def test_full_checkout_credits_buyer_then_moves_straight_to_escrow(self):
        payment, _ = services.create_payment(self.p, reference="order-1", seller=self.seller, amount="25")
        deposit = chain.open_payment(payment)
        self.assertTrue(deposit.address.startswith("T"))
        self.assertEqual(payment.status, Payment.Status.AWAITING_PAYMENT)

        self.client_.transfers = [transfer(deposit.address, 25_000_000, "a" * 64)]
        chain.scan_due_deposits(self.client_)
        services.settle_pending_payments()

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FUNDED)
        self.assertIsNotNone(payment.escrow)
        self.assertEqual(payment.escrow.status, "held")
        self.assertEqual(payment.escrow.buyer_id, payment.buyer_id)
        self.assertEqual(services.reconcile(), [])

    def test_underpayment_is_credited_but_never_auto_settled(self):
        payment, _ = services.create_payment(self.p, reference="order-2", seller=self.seller, amount="25")
        deposit = chain.open_payment(payment)
        self.client_.transfers = [transfer(deposit.address, 10_000_000, "b" * 64)]
        chain.scan_due_deposits(self.client_)
        services.settle_pending_payments()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.AWAITING_PAYMENT)
        self.assertEqual(available(self.p, payment.buyer), D("10"))  # never lost, just not enough yet

    def test_expired_unpaid_payment_is_marked_expired(self):
        payment, _ = services.create_payment(self.p, reference="order-3", seller=self.seller, amount="25", expires_in_minutes=5)
        chain.open_payment(payment)
        Payment.objects.filter(pk=payment.pk).update(expires_at=payment.created_at)
        services.settle_pending_payments()
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.EXPIRED)

    def test_same_reference_replays(self):
        first, replayed1 = services.create_payment(self.p, reference="order-4", seller=self.seller, amount="25")
        second, replayed2 = services.create_payment(self.p, reference="order-4", seller=self.seller, amount="25")
        self.assertFalse(replayed1)
        self.assertTrue(replayed2)
        self.assertEqual(first.pk, second.pk)

    def test_guest_checkout_creates_an_anonymous_buyer(self):
        payment, _ = services.create_payment(self.p, reference="order-5", seller=self.seller, amount="25")
        self.assertTrue(payment.buyer.external_id.startswith("guest:"))

    def test_standing_wallet_and_payment_addresses_do_not_collide(self):
        alice = user(self.p, "alice")
        standing = chain.get_deposit_address(alice, create=True)
        payment, _ = services.create_payment(self.p, reference="order-6", seller=self.seller, amount="25", buyer=alice)
        order_address = chain.open_payment(payment)
        self.assertNotEqual(standing.address, order_address.address)
        self.assertEqual(chain.get_deposit_address(alice).pk, standing.pk)


@override_settings(**USDT)
class PaymentAndCommissionApiTests(TestCase):
    def setUp(self):
        self.p, self.key = make_platform()
        limiter = mock.patch("ledger.views.check_rate_limit", return_value=True)
        limiter.start()
        self.addCleanup(limiter.stop)
        self.c = APIClient()
        self.c.credentials(HTTP_X_API_KEY=self.key)

    def test_commission_config_round_trip_and_cap(self):
        self.assertEqual(self.c.get("/v1/commission-config").json()["commission_bps"], 0)
        ok = self.c.put("/v1/commission-config", {"commission_bps": 500, "recipient": "treasury"}, format="json")
        self.assertEqual((ok.status_code, ok.json()["commission_bps"], ok.json()["recipient"]), (200, 500, "treasury"))
        too_high = self.c.put("/v1/commission-config", {"commission_bps": 999999}, format="json")
        self.assertEqual((too_high.status_code, too_high.json()["error"]["code"]), (400, "invalid_request"))

    def test_create_payment_over_http_returns_a_deposit_address(self):
        r = self.c.post("/v1/payments", {"reference": "order-1", "seller": "bob", "amount": "25"}, format="json")
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["status"], "awaiting_payment")
        self.assertTrue(body["deposit_address"]["address"].startswith("T"))
        self.assertEqual(self.c.get(f"/v1/payments/{body['id']}").json()["id"], body["id"])
