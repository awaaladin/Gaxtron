import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta

import bcrypt
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.api_key import ApiKey
from app.db.models.user import User

BCRYPT_ROUNDS = 12
API_KEY_PATTERN = re.compile(r"^gax_[A-Za-z0-9_-]{32,}$")


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": subject, "exp": expire, "iat": datetime.utcnow()},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        return payload.get("sub")
    except JWTError:
        return None


def generate_api_key() -> str:
    return f"gax_{secrets.token_urlsafe(32)}"


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def is_valid_api_key_format(key: str) -> bool:
    return bool(API_KEY_PATTERN.match(key))


def verify_api_key(db: Session, raw_key: str) -> User | None:
    if not raw_key or not is_valid_api_key_format(raw_key):
        return None

    key_hash = hash_api_key(raw_key)
    api_key = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        .first()
    )
    if not api_key:
        return None

    if not _constant_time_compare(api_key.key_hash, key_hash):
        return None

    user = db.query(User).filter(User.id == api_key.user_id, User.is_active.is_(True)).first()
    if user:
        api_key.last_used_at = datetime.utcnow()
        db.commit()
    return user


def sign_webhook_payload(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(
        settings.webhook_secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_webhook_signature(payload: dict, signature: str) -> bool:
    expected = sign_webhook_payload(payload)
    return _constant_time_compare(expected, signature)


def _get_fernet() -> Fernet:
    key = hashlib.sha256(settings.wallet_encryption_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_private_key(private_key: str) -> str:
    return _get_fernet().encrypt(private_key.encode("utf-8")).decode("utf-8")


def decrypt_private_key(encrypted: str) -> str:
    try:
        return _get_fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("Failed to decrypt wallet key") from e
