import pytest

from app.core.security import (
    hash_api_key,
    is_valid_api_key_format,
    sign_webhook_payload,
    verify_password,
    hash_password,
    verify_webhook_signature,
)
from app.core.url_validation import CallbackUrlError, validate_callback_url


def test_api_key_format():
    assert is_valid_api_key_format("gax_" + "a" * 32)
    assert not is_valid_api_key_format("invalid")
    assert not is_valid_api_key_format("gax_short")


def test_password_hashing():
    hashed = hash_password("SecureP@ssw0rd123")
    assert verify_password("SecureP@ssw0rd123", hashed)
    assert not verify_password("wrong", hashed)


def test_webhook_signature():
    payload = {"event": "payment.confirmed", "payment_id": 1}
    sig = sign_webhook_payload(payload)
    assert verify_webhook_signature(payload, sig)
    assert not verify_webhook_signature(payload, "tampered")


def test_callback_blocks_localhost():
    with pytest.raises(CallbackUrlError):
        validate_callback_url("http://localhost/callback")


def test_api_key_hash_deterministic():
    key = "gax_testkey_" + "x" * 32
    assert hash_api_key(key) == hash_api_key(key)
