"""Platform-facing REST API, mounted at /v1/. Authenticated with the platform's X-API-Key."""
from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.exceptions import Throttled
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.views import exception_handler as drf_exception_handler

from merchants.authentication import ApiKeyAuthentication
from merchants.rate_limit import check_rate_limit
from merchants.url_validation import CallbackUrlError, validate_callback_url

from . import chain, services
from .models import Entry, Escrow, Payment, PlatformConfig, WebhookEvent, Withdrawal
from .tron_client import TronClient
from .serializers import (
    BalanceSerializer, CommissionConfigInSerializer, CommissionConfigSerializer, DepositAddressSerializer,
    ErrorSerializer, EscrowCreateSerializer, EscrowDisputeSerializer, EscrowSerializer, EntrySerializer,
    PaymentCreateSerializer, PaymentSerializer, SandboxCreditSerializer, TransferCreateSerializer,
    TransferSerializer, UserCreateSerializer, UserSerializer, WebhookConfigInSerializer, WebhookConfigSerializer,
    WebhookEventSerializer, WithdrawalCreateSerializer, WithdrawalSerializer,
)

_CODES = {
    400: "invalid_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
    405: "method_not_allowed", 415: "unsupported_media_type", 429: "rate_limited",
}
IDEMPOTENCY = OpenApiParameter(
    "Idempotency-Key", str, OpenApiParameter.HEADER, required=False,
    description="Unique string per logical request. Retrying with the same key returns the original result.",
)


def error_handler(exc, context):
    if isinstance(exc, services.LedgerError):
        return Response({"error": {"code": exc.code, "message": exc.message}}, status=exc.http_status)
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    body = {"code": _CODES.get(response.status_code, "error"), "message": "Request failed"}
    if isinstance(response.data, dict) and isinstance(response.data.get("detail"), str):
        body["message"] = response.data["detail"]
    elif response.status_code == 400:
        body["message"] = "Invalid request parameters"
        body["fields"] = response.data
    response.data = {"error": body}
    return response


class PlatformAPIView(APIView):
    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [IsAuthenticated]
    rate = None  # (limit, window_seconds); defaults to settings.API_RATE_LIMIT

    def get_exception_handler(self):
        return error_handler

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        limit, window = self.rate or (settings.API_RATE_LIMIT, settings.API_RATE_LIMIT_WINDOW)
        if not check_rate_limit(f"v1:{self.__class__.__name__}:{request.user.id}", limit=limit, window=window):
            raise Throttled()
        self.idempotency_key  # validates the header before any work happens

    @property
    def platform(self):
        return self.request.user

    @property
    def idempotency_key(self):
        key = self.request.headers.get("Idempotency-Key")
        if key is not None and not 1 <= len(key) <= 128:
            raise services.InvalidRequest("Idempotency-Key must be 1-128 characters")
        return key


def _page(request, qs, cursor_pk):
    try:
        limit = min(max(int(request.query_params.get("limit", 50)), 1), 100)
    except ValueError:
        raise services.InvalidRequest("limit must be an integer")
    after = request.query_params.get("starting_after")
    if after:
        pk = cursor_pk(after)
        if pk is None:
            raise services.InvalidRequest("starting_after does not match any item")
        qs = qs.filter(pk__lt=pk)
    items = list(qs.order_by("-pk")[: limit + 1])
    return items[:limit], len(items) > limit


def _listing(serializer, items, has_more):
    return Response({"data": serializer(items, many=True).data, "has_more": has_more})


def _user_payload(platform, end_user):
    end_user.balance = services.balance_summary(platform, end_user)
    return UserSerializer(end_user).data


# ------------------------------------------------------------------ users


class UsersView(PlatformAPIView):
    @extend_schema(tags=["Users"], summary="Create or fetch a user", request=UserCreateSerializer,
                   responses={201: UserSerializer, 200: UserSerializer, 400: ErrorSerializer})
    def post(self, request):
        s = UserCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        end_user, created = services.get_or_create_end_user(self.platform, s.validated_data["external_id"], s.validated_data["email"])
        return Response(_user_payload(self.platform, end_user), status=201 if created else 200)


class UserDetailView(PlatformAPIView):
    @extend_schema(tags=["Users"], summary="Get a user and their balance", responses={200: UserSerializer, 404: ErrorSerializer})
    def get(self, request, external_id):
        return Response(_user_payload(self.platform, services.get_end_user(self.platform, external_id)))


class UserBalanceView(PlatformAPIView):
    @extend_schema(tags=["Users"], summary="Get a user's balance", responses={200: BalanceSerializer, 404: ErrorSerializer})
    def get(self, request, external_id):
        end_user = services.get_end_user(self.platform, external_id)
        return Response(BalanceSerializer(services.balance_summary(self.platform, end_user)).data)


class UserTransactionsView(PlatformAPIView):
    @extend_schema(tags=["Users"], summary="List a user's ledger entries (newest first)", responses={200: EntrySerializer(many=True)},
                   parameters=[OpenApiParameter("limit", int), OpenApiParameter("starting_after", int)])
    def get(self, request, external_id):
        end_user = services.get_end_user(self.platform, external_id)
        qs = Entry.objects.filter(account__platform=self.platform, account__end_user=end_user).select_related("transaction")
        items, more = _page(request, qs, lambda v: int(v) if v.isdigit() else None)
        return _listing(EntrySerializer, items, more)


def _deposit_payload(deposit):
    return DepositAddressSerializer({
        "address": deposit.address, "network": f"tron-{settings.TRON_NETWORK}", "currency": "USDT",
        "token_contract": settings.USDT_TRC20_CONTRACT, "min_deposit": settings.TRON_DEPOSIT_MIN,
    }).data


class UserDepositAddressView(PlatformAPIView):
    @extend_schema(tags=["Users"], summary="Get a user's deposit address", responses={200: DepositAddressSerializer, 404: ErrorSerializer})
    def get(self, request, external_id):
        end_user = services.get_end_user(self.platform, external_id)
        deposit = chain.get_deposit_address(end_user)
        if deposit is None:
            raise services.NotFound("This user has no deposit address yet")
        return Response(_deposit_payload(deposit))

    @extend_schema(tags=["Users"], summary="Create (or fetch) a user's USDT deposit address", request=None,
                   responses={200: DepositAddressSerializer, 503: ErrorSerializer})
    def post(self, request, external_id):
        if not settings.USDT_TRC20_CONTRACT:
            raise services.Unavailable("Deposits are not configured on this deployment")
        end_user, _ = services.get_or_create_end_user(self.platform, external_id)
        return Response(_deposit_payload(chain.get_deposit_address(end_user, create=True)))


# ------------------------------------------------------------------ transfers & sandbox


class TransfersView(PlatformAPIView):
    @extend_schema(tags=["Transfers"], summary="Move balance between two users instantly", parameters=[IDEMPOTENCY],
                   request=TransferCreateSerializer, responses={201: TransferSerializer, 402: ErrorSerializer})
    def post(self, request):
        s = TransferCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        sender = services.get_end_user(self.platform, v["from_user"])
        receiver, _ = services.get_or_create_end_user(self.platform, v["to_user"])
        txn, replayed = services.transfer(
            self.platform, sender, receiver, v["amount"], v["description"], idempotency_key=self.idempotency_key
        )
        body = {"id": txn.id, "type": "transfer", "from_user": sender.external_id, "to_user": receiver.external_id,
                "amount": v["amount"], "created_at": txn.created_at}
        return Response(TransferSerializer(body).data, status=200 if replayed else 201)


class SandboxCreditView(PlatformAPIView):
    @extend_schema(tags=["Sandbox"], summary="Fund a user with fake test USDT (testnet deployments only)",
                   parameters=[IDEMPOTENCY], request=SandboxCreditSerializer, responses={200: BalanceSerializer, 404: ErrorSerializer})
    def post(self, request):
        s = SandboxCreditSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        end_user, _ = services.get_or_create_end_user(self.platform, s.validated_data["user"])
        services.sandbox_credit(self.platform, end_user, s.validated_data["amount"], self.idempotency_key)
        return Response(BalanceSerializer(services.balance_summary(self.platform, end_user)).data)


# ------------------------------------------------------------------ escrow


class EscrowsView(PlatformAPIView):
    @extend_schema(tags=["Escrow"], summary="Hold funds in escrow (buyer pays)", request=EscrowCreateSerializer,
                   responses={201: EscrowSerializer, 200: EscrowSerializer, 402: ErrorSerializer, 409: ErrorSerializer})
    def post(self, request):
        s = EscrowCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        buyer = services.get_end_user(self.platform, v["buyer"])
        seller, _ = services.get_or_create_end_user(self.platform, v["seller"])
        escrow, replayed = services.hold_escrow(
            self.platform, buyer=buyer, seller=seller, amount=v["amount"], reference=v["reference"], metadata=v["metadata"]
        )
        return Response(EscrowSerializer(escrow).data, status=200 if replayed else 201)

    @extend_schema(tags=["Escrow"], summary="List escrows", responses={200: EscrowSerializer(many=True)},
                   parameters=[OpenApiParameter("status", str), OpenApiParameter("reference", str), OpenApiParameter("buyer", str),
                               OpenApiParameter("seller", str), OpenApiParameter("limit", int), OpenApiParameter("starting_after", str)])
    def get(self, request):
        qs = Escrow.objects.filter(platform=self.platform).select_related("buyer", "seller")
        p = request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("reference"):
            qs = qs.filter(reference=p["reference"])
        if p.get("buyer"):
            qs = qs.filter(buyer__external_id=p["buyer"])
        if p.get("seller"):
            qs = qs.filter(seller__external_id=p["seller"])
        cursor = lambda v: Escrow.objects.filter(platform=self.platform, public_id=v).values_list("pk", flat=True).first()  # noqa: E731
        items, more = _page(request, qs, cursor)
        return _listing(EscrowSerializer, items, more)


def _escrow(platform, escrow_id):
    escrow = Escrow.objects.select_related("buyer", "seller").filter(platform=platform, public_id=escrow_id).first()
    if not escrow:
        raise services.NotFound("Escrow not found")
    return escrow


class EscrowDetailView(PlatformAPIView):
    @extend_schema(tags=["Escrow"], summary="Get an escrow", responses={200: EscrowSerializer, 404: ErrorSerializer})
    def get(self, request, escrow_id):
        return Response(EscrowSerializer(_escrow(self.platform, escrow_id)).data)


class EscrowReleaseView(PlatformAPIView):
    @extend_schema(tags=["Escrow"], summary="Release funds to the seller", request=None,
                   responses={200: EscrowSerializer, 409: ErrorSerializer})
    def post(self, request, escrow_id):
        escrow, _ = services.release_escrow(self.platform, escrow_id)
        return Response(EscrowSerializer(escrow).data)


class EscrowRefundView(PlatformAPIView):
    @extend_schema(tags=["Escrow"], summary="Refund the buyer in full", request=None,
                   responses={200: EscrowSerializer, 409: ErrorSerializer})
    def post(self, request, escrow_id):
        escrow, _ = services.refund_escrow(self.platform, escrow_id)
        return Response(EscrowSerializer(escrow).data)


class EscrowDisputeView(PlatformAPIView):
    @extend_schema(tags=["Escrow"], summary="Flag an escrow as disputed (freezes auto-resolution on your side)",
                   request=EscrowDisputeSerializer, responses={200: EscrowSerializer, 409: ErrorSerializer})
    def post(self, request, escrow_id):
        s = EscrowDisputeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        escrow, _ = services.dispute_escrow(self.platform, escrow_id, s.validated_data["reason"])
        return Response(EscrowSerializer(escrow).data)


# ------------------------------------------------------------------ payments (pay from any wallet)


class PaymentsView(PlatformAPIView):
    @extend_schema(tags=["Payments"], summary="Open a pay-from-any-wallet checkout for one order",
                   parameters=[IDEMPOTENCY], request=PaymentCreateSerializer,
                   responses={201: PaymentSerializer, 200: PaymentSerializer, 400: ErrorSerializer})
    def post(self, request):
        s = PaymentCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        seller, _ = services.get_or_create_end_user(self.platform, v["seller"])
        buyer = services.get_end_user(self.platform, v["buyer"]) if v.get("buyer") else None
        payment, replayed = services.create_payment(
            self.platform, reference=v["reference"], seller=seller, buyer=buyer, amount=v["amount"],
            expires_in_minutes=v.get("expires_in_minutes"), commission_bps=v.get("commission_bps"),
            metadata=v["metadata"],
        )
        chain.open_payment(payment)
        payment.refresh_from_db()
        return Response(PaymentSerializer(payment).data, status=200 if replayed else 201)

    @extend_schema(tags=["Payments"], summary="List payments", responses={200: PaymentSerializer(many=True)},
                   parameters=[OpenApiParameter("status", str), OpenApiParameter("reference", str),
                               OpenApiParameter("limit", int), OpenApiParameter("starting_after", str)])
    def get(self, request):
        qs = Payment.objects.filter(platform=self.platform).select_related("buyer", "seller", "escrow", "deposit_address")
        p = request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("reference"):
            qs = qs.filter(reference=p["reference"])
        cursor = lambda v: Payment.objects.filter(platform=self.platform, public_id=v).values_list("pk", flat=True).first()  # noqa: E731
        items, more = _page(request, qs, cursor)
        return _listing(PaymentSerializer, items, more)


class PaymentDetailView(PlatformAPIView):
    @extend_schema(tags=["Payments"], summary="Get a payment (checks for a new deposit immediately)",
                   responses={200: PaymentSerializer, 404: ErrorSerializer})
    def get(self, request, payment_id):
        payment = Payment.objects.select_related("buyer", "seller", "deposit_address").filter(
            platform=self.platform, public_id=payment_id
        ).first()
        if not payment:
            raise services.NotFound("Payment not found")
        if payment.status == Payment.Status.AWAITING_PAYMENT:
            try:
                chain.scan_deposit(TronClient(), payment.deposit_address)
            except Exception:
                pass
            payment = services.settle_payment(payment.pk) or payment
        return Response(PaymentSerializer(payment).data)


# ------------------------------------------------------------------ commission config


class CommissionConfigView(PlatformAPIView):
    @extend_schema(tags=["Settings"], summary="Get your commission settings", responses={200: CommissionConfigSerializer})
    def get(self, request):
        config = _config(self.platform)
        return Response(CommissionConfigSerializer({
            "commission_bps": config.commission_bps, "max_commission_bps": settings.MAX_COMMISSION_BPS,
            "recipient": config.commission_recipient.external_id if config.commission_recipient_id else None,
            "gateway_fee_bps": services.gateway_fee_bps(self.platform),
        }).data)

    @extend_schema(tags=["Settings"], summary="Set your default commission on each sale",
                   request=CommissionConfigInSerializer, responses={200: CommissionConfigSerializer, 400: ErrorSerializer})
    def put(self, request):
        s = CommissionConfigInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        if v["commission_bps"] > settings.MAX_COMMISSION_BPS:
            raise services.InvalidRequest(f"commission_bps must be at most {settings.MAX_COMMISSION_BPS}")
        config = _config(self.platform)
        config.commission_bps = v["commission_bps"]
        config.commission_recipient = services.get_or_create_end_user(self.platform, v["recipient"])[0] if v.get("recipient") else None
        config.save(update_fields=["commission_bps", "commission_recipient"])
        return self.get(request)


# ------------------------------------------------------------------ withdrawals


class WithdrawalsView(PlatformAPIView):
    rate = (10, 60)

    @extend_schema(tags=["Withdrawals"], summary="Withdraw USDT (TRC-20) to an external address", parameters=[IDEMPOTENCY],
                   request=WithdrawalCreateSerializer,
                   responses={201: WithdrawalSerializer, 200: WithdrawalSerializer, 402: ErrorSerializer, 422: ErrorSerializer})
    def post(self, request):
        s = WithdrawalCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        end_user = services.get_end_user(self.platform, v["user"])
        withdrawal, replayed = services.request_withdrawal(
            self.platform, end_user, v["amount"], v["destination"], idempotency_key=self.idempotency_key
        )
        return Response(WithdrawalSerializer(withdrawal).data, status=200 if replayed else 201)

    @extend_schema(tags=["Withdrawals"], summary="List withdrawals", responses={200: WithdrawalSerializer(many=True)},
                   parameters=[OpenApiParameter("user", str), OpenApiParameter("status", str), OpenApiParameter("limit", int),
                               OpenApiParameter("starting_after", str)])
    def get(self, request):
        qs = Withdrawal.objects.filter(platform=self.platform).select_related("end_user")
        p = request.query_params
        if p.get("user"):
            qs = qs.filter(end_user__external_id=p["user"])
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        cursor = lambda v: Withdrawal.objects.filter(platform=self.platform, public_id=v).values_list("pk", flat=True).first()  # noqa: E731
        items, more = _page(request, qs, cursor)
        return _listing(WithdrawalSerializer, items, more)


class WithdrawalDetailView(PlatformAPIView):
    @extend_schema(tags=["Withdrawals"], summary="Get a withdrawal", responses={200: WithdrawalSerializer, 404: ErrorSerializer})
    def get(self, request, withdrawal_id):
        withdrawal = Withdrawal.objects.select_related("end_user").filter(platform=self.platform, public_id=withdrawal_id).first()
        if not withdrawal:
            raise services.NotFound("Withdrawal not found")
        return Response(WithdrawalSerializer(withdrawal).data)


class WithdrawalCancelView(PlatformAPIView):
    @extend_schema(tags=["Withdrawals"], summary="Cancel a withdrawal that has not been broadcast", request=None,
                   responses={200: WithdrawalSerializer, 409: ErrorSerializer})
    def post(self, request, withdrawal_id):
        return Response(WithdrawalSerializer(services.cancel_withdrawal(self.platform, withdrawal_id)).data)


# ------------------------------------------------------------------ webhooks


def _config(platform):
    config, _ = PlatformConfig.objects.get_or_create(platform=platform)
    return config


def _config_payload(config):
    return WebhookConfigSerializer({"url": config.webhook_url, "signing_secret": config.signing_secret}).data


class WebhookConfigView(PlatformAPIView):
    @extend_schema(tags=["Webhooks"], summary="Get your webhook endpoint and signing secret", responses={200: WebhookConfigSerializer})
    def get(self, request):
        return Response(_config_payload(_config(self.platform)))

    @extend_schema(tags=["Webhooks"], summary="Set (or clear) your webhook endpoint", request=WebhookConfigInSerializer,
                   responses={200: WebhookConfigSerializer, 400: ErrorSerializer})
    def put(self, request):
        s = WebhookConfigInSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        url = s.validated_data["url"].strip()
        if url:
            try:
                validate_callback_url(url)
            except CallbackUrlError as exc:
                raise services.InvalidRequest(str(exc))
        config = _config(self.platform)
        config.webhook_url = url
        config.save(update_fields=["webhook_url"])
        return Response(_config_payload(config))


class WebhookSecretRotateView(PlatformAPIView):
    rate = (5, 60)

    @extend_schema(tags=["Webhooks"], summary="Rotate the signing secret (the old one stops working immediately)", request=None,
                   responses={200: WebhookConfigSerializer})
    def post(self, request):
        config = _config(self.platform)
        config.rotate_secret()
        return Response(_config_payload(config))


class WebhookEventsView(PlatformAPIView):
    @extend_schema(tags=["Webhooks"], summary="List recent webhook events and their delivery status",
                   responses={200: WebhookEventSerializer(many=True)},
                   parameters=[OpenApiParameter("limit", int), OpenApiParameter("starting_after", str)])
    def get(self, request):
        qs = WebhookEvent.objects.filter(platform=self.platform)
        cursor = lambda v: qs.filter(event_id=v).values_list("pk", flat=True).first()  # noqa: E731
        items, more = _page(request, qs, cursor)
        return _listing(WebhookEventSerializer, items, more)
