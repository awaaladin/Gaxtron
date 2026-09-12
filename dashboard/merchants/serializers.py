"""DRF serializers mirroring GaX/app/schemas/{auth,api_key,payment}.py field-for-field."""
from decimal import Decimal

from rest_framework import serializers

from .models import ApiKey

MAX_PAYMENT_AMOUNT = Decimal("1000000")


class RegisterRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(min_length=3, max_length=100)
    password = serializers.CharField(min_length=8, max_length=128)


class TokenResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    token_type = serializers.CharField(default="bearer")


class UserResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.CharField()
    username = serializers.CharField()
    is_active = serializers.BooleanField()
    wallet_address = serializers.CharField(allow_null=True, required=False)


class WalletNonceResponseSerializer(serializers.Serializer):
    nonce = serializers.CharField()
    message = serializers.CharField()


class WalletVerifyRequestSerializer(serializers.Serializer):
    address = serializers.CharField()
    signature = serializers.CharField()
    nonce = serializers.CharField()


class ApiKeyCreateRequestSerializer(serializers.Serializer):
    name = serializers.CharField(default="default", max_length=100, required=False)


class ApiKeyResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiKey
        fields = ["id", "key_prefix", "name", "is_active", "created_at", "last_used_at"]


class ApiKeyCreatedResponseSerializer(ApiKeyResponseSerializer):
    api_key = serializers.CharField()

    class Meta(ApiKeyResponseSerializer.Meta):
        fields = ApiKeyResponseSerializer.Meta.fields + ["api_key"]


class CreatePaymentRequestSerializer(serializers.Serializer):
    # Accepted as a JSON string or number, same as FastAPI's Decimal field did.
    amount = serializers.DecimalField(max_digits=36, decimal_places=18, min_value=Decimal("0.000000000000000001"))
    callback_url = serializers.URLField()
    idempotency_key = serializers.RegexField(r"^[a-zA-Z0-9_-]+$", min_length=8, max_length=64, required=False, allow_null=True)

    def validate_amount(self, value):
        if value > MAX_PAYMENT_AMOUNT:
            raise serializers.ValidationError(f"Amount cannot exceed {MAX_PAYMENT_AMOUNT}")
        return value


class CreatePaymentResponseSerializer(serializers.Serializer):
    payment_id = serializers.IntegerField(source="id")
    payment_token = serializers.SerializerMethodField()
    payment_url = serializers.SerializerMethodField()
    checkout_url = serializers.SerializerMethodField()
    wallet_address = serializers.CharField()
    amount = serializers.DecimalField(max_digits=36, decimal_places=18)
    currency = serializers.CharField()
    chain = serializers.CharField()
    status = serializers.CharField()
    callback_url = serializers.CharField()
    tx_hash = serializers.CharField(allow_null=True)
    confirmations = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField(allow_null=True)

    def get_payment_token(self, obj):
        return obj.public_token or str(obj.id)

    def get_payment_url(self, obj):
        from .payment_service import PaymentService
        return PaymentService.build_payment_url(obj)

    def get_checkout_url(self, obj):
        return self.get_payment_url(obj)


class PaymentResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=36, decimal_places=18)
    chain = serializers.CharField()
    currency = serializers.CharField()
    status = serializers.CharField()
    wallet_address = serializers.CharField()
    callback_url = serializers.CharField()
    tx_hash = serializers.CharField(allow_null=True)
    confirmations = serializers.IntegerField()
    payment_url = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    confirmed_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)

    def get_payment_url(self, obj):
        from .payment_service import PaymentService
        return PaymentService.build_payment_url(obj)


class VerifyPaymentResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=36, decimal_places=18)
    chain = serializers.CharField()
    currency = serializers.CharField()
    wallet_address = serializers.CharField()
    tx_hash = serializers.CharField(allow_null=True)
    confirmations = serializers.IntegerField()
    payment_url = serializers.SerializerMethodField()
    confirmed_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)

    def get_payment_url(self, obj):
        from .payment_service import PaymentService
        return PaymentService.build_payment_url(obj)


class PublicPaymentStatusSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    public_token = serializers.CharField(allow_null=True)
    amount = serializers.DecimalField(max_digits=36, decimal_places=18)
    currency = serializers.CharField()
    chain = serializers.CharField()
    status = serializers.CharField()
    wallet_address = serializers.CharField()
    address = serializers.SerializerMethodField()
    tx_hash = serializers.CharField(allow_null=True)
    confirmations = serializers.IntegerField()
    required_confirmations = serializers.SerializerMethodField()
    network = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    confirmed_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)

    def get_address(self, obj):
        return obj.wallet_address

    def get_required_confirmations(self, obj):
        from django.conf import settings
        return settings.ETH_REQUIRED_CONFIRMATIONS

    def get_network(self, obj):
        from django.conf import settings
        return settings.BLOCKCHAIN_NETWORK
