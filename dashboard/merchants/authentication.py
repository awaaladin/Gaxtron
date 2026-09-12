"""
DRF authentication classes mirroring GaX/app/api/deps.py's split exactly:
- JWTAuthentication: Bearer token — used for /auth/me and API-key management.
- ApiKeyAuthentication: X-API-Key header — used for payment-mutating endpoints.
Payment endpoints must NOT accept a JWT, and API-key management must NOT accept an API key —
same intentional split as the FastAPI version, not an oversight.
"""
from rest_framework import authentication, exceptions

from . import security
from .models import GaxtronUser


class JWTAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[len("Bearer "):].strip()
        email = security.decode_access_token(token)
        if not email:
            raise exceptions.AuthenticationFailed("Invalid or expired token")
        try:
            user = GaxtronUser.objects.get(email=email, is_active=True)
        except GaxtronUser.DoesNotExist:
            raise exceptions.AuthenticationFailed("User not found or suspended")
        return (user, token)


class ApiKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return None
        if not security.is_valid_api_key_format(api_key):
            raise exceptions.AuthenticationFailed("Valid API key required")
        user = security.verify_api_key(api_key)
        if not user:
            raise exceptions.AuthenticationFailed("Invalid or revoked API key")
        return (user, api_key)

    def authenticate_header(self, request):
        return "ApiKey"
