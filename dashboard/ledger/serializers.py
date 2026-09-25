import json
from decimal import Decimal

from rest_framework import serializers

from .models import Entry, Escrow, WebhookEvent, Withdrawal

AMOUNT_IN = {"max_digits": 30, "decimal_places": 6, "min_value": Decimal("0.000001")}
AMOUNT_OUT = {"max_digits": 30, "decimal_places": 6}


def _validate_metadata(value):
    if len(json.dumps(value)) > 2000:
        raise serializers.ValidationError("metadata must be under 2000 characters when serialized")
    return value


class ErrorBodySerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()


class ErrorSerializer(serializers.Serializer):
    error = ErrorBodySerializer()


class UserCreateSerializer(serializers.Serializer):
    external_id = serializers.CharField(max_length=128, help_text="Your own identifier for this user.")
    email = serializers.EmailField(required=False, allow_blank=True, default="")


class BalanceSerializer(serializers.Serializer):
    currency = serializers.CharField()
    available = serializers.DecimalField(**AMOUNT_OUT, help_text="Spendable now.")
    held_as_buyer = serializers.DecimalField(**AMOUNT_OUT, help_text="Locked in open escrows this user funded.")
    incoming_as_seller = serializers.DecimalField(**AMOUNT_OUT, help_text="Held in open escrows awaiting release to this user.")
    pending_withdrawals = serializers.DecimalField(**AMOUNT_OUT, help_text="Reserved for in-flight withdrawals.")


class UserSerializer(serializers.Serializer):
    id = serializers.CharField(source="external_id")
    email = serializers.CharField()
    created_at = serializers.DateTimeField()
    balance = BalanceSerializer(required=False)


class EntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.CharField(source="transaction.kind")
    amount = serializers.DecimalField(**AMOUNT_OUT, help_text="Signed: positive credits the user, negative debits.")
    reference = serializers.CharField(source="transaction.reference")
    description = serializers.CharField(source="transaction.description")
    created_at = serializers.DateTimeField()


class TransferCreateSerializer(serializers.Serializer):
    from_user = serializers.CharField(max_length=128)
    to_user = serializers.CharField(max_length=128)
    amount = serializers.DecimalField(**AMOUNT_IN)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class TransferSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    type = serializers.CharField()
    from_user = serializers.CharField()
    to_user = serializers.CharField()
    amount = serializers.DecimalField(**AMOUNT_OUT)
    created_at = serializers.DateTimeField()


class SandboxCreditSerializer(serializers.Serializer):
    user = serializers.CharField(max_length=128)
    amount = serializers.DecimalField(**AMOUNT_IN)


class EscrowCreateSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=128, help_text="Your order id. Unique per platform; makes creation idempotent.")
    buyer = serializers.CharField(max_length=128)
    seller = serializers.CharField(max_length=128)
    amount = serializers.DecimalField(**AMOUNT_IN)
    metadata = serializers.DictField(required=False, default=dict, validators=[_validate_metadata])


class EscrowDisputeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


class EscrowSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="public_id")
    buyer = serializers.CharField(source="buyer.external_id")
    seller = serializers.CharField(source="seller.external_id")
    amount = serializers.DecimalField(**AMOUNT_OUT)
    fee = serializers.DecimalField(**AMOUNT_OUT)

    class Meta:
        model = Escrow
        fields = [
            "id", "reference", "status", "buyer", "seller", "amount", "fee", "currency",
            "metadata", "dispute_reason", "created_at", "resolved_at",
        ]


class WithdrawalCreateSerializer(serializers.Serializer):
    user = serializers.CharField(max_length=128)
    amount = serializers.DecimalField(**AMOUNT_IN)
    destination = serializers.CharField(max_length=64, help_text="TRON (TRC-20) address, starts with T.")


class WithdrawalSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="public_id")
    user = serializers.CharField(source="end_user.external_id")
    amount = serializers.DecimalField(**AMOUNT_OUT)
    fee = serializers.DecimalField(**AMOUNT_OUT)
    net_amount = serializers.DecimalField(**AMOUNT_OUT, read_only=True)

    class Meta:
        model = Withdrawal
        fields = [
            "id", "user", "amount", "fee", "net_amount", "currency", "destination", "status",
            "tx_hash", "failure_reason", "created_at", "updated_at",
        ]


class WebhookConfigInSerializer(serializers.Serializer):
    url = serializers.CharField(allow_blank=True, max_length=2000, help_text="HTTPS endpoint, or empty to disable webhooks.")


class WebhookConfigSerializer(serializers.Serializer):
    url = serializers.CharField()
    signing_secret = serializers.CharField(help_text="Use it to verify the X-Gaxtron-Signature header.")


class WebhookEventSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="event_id")
    payload = serializers.SerializerMethodField()

    class Meta:
        model = WebhookEvent
        fields = ["id", "type", "status", "attempts", "response_code", "created_at", "delivered_at", "payload"]

    def get_payload(self, obj) -> dict:
        return json.loads(obj.payload)
