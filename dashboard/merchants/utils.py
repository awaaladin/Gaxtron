"""Sync Django merchants with shared Gaxtron users table."""
from datetime import datetime

import bcrypt
from django.contrib.auth.models import User

from merchants.models import GaxtronUser


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def ensure_gaxtron_merchant(email: str, username: str, password: str) -> GaxtronUser:
    email = email.lower().strip()
    existing = GaxtronUser.objects.filter(email=email).first()
    if existing:
        return existing
    return GaxtronUser.objects.create(
        email=email,
        username=username.strip(),
        hashed_password=hash_password(password),
        is_active=True,
        is_superadmin=False,
        created_at=datetime.utcnow(),
    )


def ensure_django_user(email: str, username: str, password: str) -> User:
    email = email.lower().strip()
    user = User.objects.filter(email=email).first()
    if user:
        return user
    return User.objects.create_user(
        username=username.strip(),
        email=email,
        password=password,
    )
