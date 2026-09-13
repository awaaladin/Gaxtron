"""
Security regression tests — ported from GaX/tests/test_security.py (the only tests that
existed before the Django migration), plus a couple of additions (JWT and Fernet wallet-key
roundtrips) covering code that's now central to this port and wasn't covered before.

Run with: python manage.py test merchants
"""
from django.test import TestCase

from . import security
from .url_validation import CallbackUrlError, validate_callback_url


class SecurityPrimitivesTests(TestCase):
    def test_api_key_format(self):
        self.assertTrue(security.is_valid_api_key_format("gax_" + "a" * 32))
        self.assertFalse(security.is_valid_api_key_format("invalid"))
        self.assertFalse(security.is_valid_api_key_format("gax_short"))

    def test_password_hashing(self):
        hashed = security.hash_password("SecureP@ssw0rd123")
        self.assertTrue(security.verify_password("SecureP@ssw0rd123", hashed))
        self.assertFalse(security.verify_password("wrong", hashed))

    def test_webhook_signature(self):
        payload = {"event": "payment.confirmed", "payment_id": 1}
        sig = security.sign_webhook_payload(payload)
        self.assertTrue(security.verify_webhook_signature(payload, sig))
        self.assertFalse(security.verify_webhook_signature(payload, "tampered"))

    def test_api_key_hash_deterministic(self):
        key = "gax_testkey_" + "x" * 32
        self.assertEqual(security.hash_api_key(key), security.hash_api_key(key))

    def test_jwt_roundtrip(self):
        token = security.create_access_token("merchant@example.com")
        self.assertEqual(security.decode_access_token(token), "merchant@example.com")

    def test_jwt_rejects_garbage(self):
        self.assertIsNone(security.decode_access_token("not-a-real-token"))

    def test_wallet_key_encryption_roundtrip(self):
        raw_key = "0x" + "ab" * 32
        encrypted = security.encrypt_private_key(raw_key)
        self.assertNotEqual(encrypted, raw_key)
        self.assertEqual(security.decrypt_private_key(encrypted), raw_key)


class CallbackUrlValidationTests(TestCase):
    def test_blocks_localhost(self):
        with self.assertRaises(CallbackUrlError):
            validate_callback_url("http://localhost/callback")

    def test_blocks_loopback_ip(self):
        with self.assertRaises(CallbackUrlError):
            validate_callback_url("http://127.0.0.1/callback")

    def test_blocks_non_http_scheme(self):
        with self.assertRaises(CallbackUrlError):
            validate_callback_url("ftp://example.com/callback")

    def test_allows_public_https(self):
        # webhook.site resolves publicly; this exercises the real DNS-resolution path.
        validate_callback_url("https://webhook.site/callback")
