"""
Real Django ORM models for the Gaxtron payment engine — replaces the FastAPI/SQLAlchemy
models this app used to only mirror read-only. Table names/columns match the original
SQLAlchemy schema exactly (see GaX/app/db/models/*.py, kept there for reference during the
migration) so existing rows in the shared database keep working without a data migration —
only the *framework* reading/writing them changes.
"""
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models


class GaxtronUserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        if not username:
            raise ValueError("Username is required")
        user = self.model(email=self.normalize_email(email).lower(), username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(email, username, password, **extra_fields)


class GaxtronUser(AbstractBaseUser):
    """The real `users` table — merchants. Bcrypt hashing is ours (security.py), not
    Django's pluggable hasher framework; `password` is redeclared only to point Django's
    built-in auth machinery (AbstractBaseUser, login()) at the real `hashed_password` column."""

    id = models.AutoField(primary_key=True)
    email = models.CharField(max_length=255, unique=True)
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=255, db_column="hashed_password")
    wallet_address = models.CharField(max_length=42, unique=True, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False, db_column="is_superadmin")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = GaxtronUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.username

    # --- bcrypt auth, matching GaX/app/core/security.py exactly ---
    def check_password(self, raw_password):
        from .security import verify_password
        return verify_password(raw_password, self.password)

    def set_password(self, raw_password):
        from .security import hash_password
        self.password = hash_password(raw_password)

    def has_usable_password(self):
        return bool(self.password)

    @property
    def is_staff(self):
        return self.is_superuser


class ApiKey(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(GaxtronUser, on_delete=models.CASCADE, db_column="user_id", related_name="api_keys")
    key_hash = models.CharField(max_length=255, db_index=True)
    key_prefix = models.CharField(max_length=12)
    name = models.CharField(max_length=100, default="default")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "api_keys"

    def __str__(self):
        return f"{self.key_prefix}..."


class Payment(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(GaxtronUser, on_delete=models.CASCADE, db_column="user_id", related_name="payments")
    amount = models.DecimalField(max_digits=36, decimal_places=18)
    chain = models.CharField(max_length=10, default="ETH", db_index=True)
    currency = models.CharField(max_length=10)
    status = models.CharField(max_length=20, default="pending", db_index=True)
    wallet_address = models.CharField(max_length=128, db_index=True)
    callback_url = models.TextField()
    idempotency_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    tx_hash = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    confirmations = models.IntegerField(default=0)
    last_scanned_block = models.IntegerField(null=True, blank=True)
    public_token = models.CharField(max_length=72, unique=True, null=True, blank=True, db_index=True)
    event_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]


class Transaction(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(GaxtronUser, on_delete=models.CASCADE, db_column="user_id", related_name="transactions")
    payment = models.ForeignKey(
        Payment, on_delete=models.SET_NULL, db_column="payment_id", null=True, blank=True, related_name="transactions"
    )
    tx_hash = models.CharField(max_length=128, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=36, decimal_places=18)
    chain = models.CharField(max_length=10, default="ETH")
    currency = models.CharField(max_length=10)
    from_address = models.CharField(max_length=128)
    to_address = models.CharField(max_length=128)
    status = models.CharField(max_length=20, default="pending", db_index=True)
    confirmations = models.IntegerField(default=0)
    block_number = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transactions"
        ordering = ["-created_at"]


class Wallet(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        GaxtronUser, on_delete=models.SET_NULL, db_column="user_id", null=True, blank=True, related_name="wallets"
    )
    payment = models.ForeignKey(
        Payment, on_delete=models.SET_NULL, db_column="payment_id", null=True, blank=True, related_name="wallets"
    )
    address = models.CharField(max_length=128, unique=True, db_index=True)
    encrypted_private_key = models.TextField()
    chain = models.CharField(max_length=10, default="ETH")
    currency = models.CharField(max_length=10)
    balance = models.DecimalField(max_digits=36, decimal_places=18, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "wallets"


class WalletAuthNonce(models.Model):
    id = models.AutoField(primary_key=True)
    nonce = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "wallet_auth_nonces"


class WebhookLog(models.Model):
    id = models.AutoField(primary_key=True)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, db_column="payment_id", related_name="webhook_logs")
    event_id = models.CharField(max_length=64, unique=True, db_index=True)
    callback_url = models.TextField()
    payload = models.TextField()
    status = models.CharField(max_length=20, default="pending")
    response_code = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "webhook_logs"
        ordering = ["-created_at"]
