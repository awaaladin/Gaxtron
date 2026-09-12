"""
REST API views — the Django replacement for GaX/app/api/routers/{auth,api_keys}.py.
Paths/payloads are reproduced exactly (see config/api_urls.py) so frontend/js/api.js and the
Android app work against this unmodified.
"""
import logging

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied, Throttled
from rest_framework.response import Response
from rest_framework.views import APIView

from . import security
from .authentication import ApiKeyAuthentication, JWTAuthentication
from .models import ApiKey, GaxtronUser, WalletAuthNonce
from .rate_limit import check_auth_rate_limit
from .serializers import (
    ApiKeyCreateRequestSerializer,
    ApiKeyResponseSerializer,
    RegisterRequestSerializer,
    TokenResponseSerializer,
    UserResponseSerializer,
    WalletNonceResponseSerializer,
    WalletVerifyRequestSerializer,
)
from . import wallet_auth
from django.conf import settings

logger = logging.getLogger(__name__)


def _client_ip(request):
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _rate_limit_auth(request):
    if not check_auth_rate_limit(_client_ip(request)):
        raise Throttled(detail="Too many authentication attempts")


def _token_response(user, status_code=status.HTTP_200_OK) -> Response:
    token = security.create_access_token(user.email)
    body = TokenResponseSerializer({"access_token": token, "token_type": "bearer"}).data
    return Response(body, status=status_code)


class RegisterView(APIView):
    def post(self, request):
        _rate_limit_auth(request)
        data = RegisterRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        email = data.validated_data["email"].lower().strip()
        username = data.validated_data["username"].strip()

        if GaxtronUser.objects.filter(email=email).exists() or GaxtronUser.objects.filter(username=username).exists():
            return Response({"detail": "Email or username already registered"}, status=status.HTTP_400_BAD_REQUEST)

        user = GaxtronUser.objects.create_user(email=email, username=username, password=data.validated_data["password"])
        logger.info("User registered: %s", user.id)
        return _token_response(user, status.HTTP_201_CREATED)


class LoginView(APIView):
    def post(self, request):
        _rate_limit_auth(request)
        email = str(request.data.get("username", "")).lower().strip()
        password = request.data.get("password", "")
        user = GaxtronUser.objects.filter(email=email).first()
        if not user or not user.check_password(password):
            raise AuthenticationFailed("Invalid credentials")
        if not user.is_active:
            raise PermissionDenied("Account suspended")
        token = security.create_access_token(user.email)
        body = TokenResponseSerializer({"access_token": token, "token_type": "bearer"}).data
        return Response(body)


class WalletNonceView(APIView):
    def get(self, request):
        _rate_limit_auth(request)
        WalletAuthNonce.objects.filter(expires_at__lt=timezone.now()).delete()
        nonce = wallet_auth.generate_nonce()
        WalletAuthNonce.objects.create(nonce=nonce, expires_at=wallet_auth.nonce_expires_at())
        message = wallet_auth.build_sign_message(nonce)
        return Response(WalletNonceResponseSerializer({"nonce": nonce, "message": message}).data)


class WalletVerifyView(APIView):
    def post(self, request):
        _rate_limit_auth(request)
        data = WalletVerifyRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        body = data.validated_data

        if not wallet_auth.is_valid_eth_address(body["address"]):
            return Response({"detail": "Invalid wallet address"}, status=status.HTTP_400_BAD_REQUEST)

        address = wallet_auth.normalize_address(body["address"])
        message = wallet_auth.build_sign_message(body["nonce"].strip())

        if not wallet_auth.verify_wallet_signature(body["address"], body["signature"], message):
            raise AuthenticationFailed("Invalid signature")

        record = WalletAuthNonce.objects.filter(nonce=body["nonce"].strip(), used_at__isnull=True).first()
        if not record or record.expires_at < timezone.now():
            raise AuthenticationFailed("Nonce expired or invalid")
        record.used_at = timezone.now()
        record.save(update_fields=["used_at"])

        user = GaxtronUser.objects.filter(wallet_address=address).first()
        if not user:
            import secrets as _secrets

            short = address[2:10]
            email = f"{address}@wallet.gaxtron"
            username = f"wallet_{short}"
            base_username = username
            n = 1
            while GaxtronUser.objects.filter(username=username).exists():
                username = f"{base_username}_{n}"
                n += 1
            user = GaxtronUser.objects.create_user(
                email=email, username=username, password=_secrets.token_urlsafe(32)
            )
            user.wallet_address = address
            user.save(update_fields=["wallet_address"])
            logger.info("Wallet user created: %s", address)
        elif not user.is_active:
            raise PermissionDenied("Account suspended")

        return _token_response(user)


class MeView(APIView):
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        if not request.user or not request.user.is_authenticated:
            raise AuthenticationFailed("Bearer token required")
        return Response(UserResponseSerializer(request.user).data)


class ApiKeysView(APIView):
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        keys = ApiKey.objects.filter(user=request.user).order_by("-created_at")
        return Response(ApiKeyResponseSerializer(keys, many=True).data)

    def post(self, request):
        active_count = ApiKey.objects.filter(user=request.user, is_active=True).count()
        if active_count >= settings.MAX_API_KEYS_PER_USER:
            return Response(
                {"detail": f"Maximum {settings.MAX_API_KEYS_PER_USER} active API keys allowed"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        data = ApiKeyCreateRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        name = data.validated_data.get("name") or "default"

        raw_key = security.generate_api_key()
        api_key = ApiKey.objects.create(
            user=request.user, key_hash=security.hash_api_key(raw_key), key_prefix=raw_key[:12], name=name
        )
        logger.info("API key created for user %s prefix=%s", request.user.id, api_key.key_prefix)
        body = ApiKeyResponseSerializer(api_key).data
        body["api_key"] = raw_key
        return Response(body, status=status.HTTP_201_CREATED)


class ApiKeyDetailView(APIView):
    authentication_classes = [JWTAuthentication]

    def delete(self, request, key_id: int):
        api_key = ApiKey.objects.filter(id=key_id, user=request.user).first()
        if not api_key:
            raise NotFound("API key not found")
        api_key.is_active = False
        api_key.save(update_fields=["is_active"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ApiKeyRegenerateView(APIView):
    authentication_classes = [JWTAuthentication]

    def post(self, request, key_id: int):
        api_key = ApiKey.objects.filter(id=key_id, user=request.user).first()
        if not api_key:
            raise NotFound("API key not found")

        active_count = ApiKey.objects.filter(user=request.user, is_active=True).count()
        if active_count >= settings.MAX_API_KEYS_PER_USER:
            api_key.is_active = False

        raw_key = security.generate_api_key()
        new_key = ApiKey.objects.create(
            user=request.user, key_hash=security.hash_api_key(raw_key), key_prefix=raw_key[:12], name=api_key.name
        )
        api_key.is_active = False
        api_key.save(update_fields=["is_active"])

        body = ApiKeyResponseSerializer(new_key).data
        body["api_key"] = raw_key
        return Response(body)
