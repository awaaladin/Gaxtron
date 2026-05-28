"""
Read-only Django models mapped to FastAPI-owned PostgreSQL tables.
Django MUST NOT process payments — display and admin only.
"""
from django.db import models


class GaxtronUser(models.Model):
    id = models.AutoField(primary_key=True)
    email = models.CharField(max_length=255)
    username = models.CharField(max_length=100)
    hashed_password = models.CharField(max_length=255)
    wallet_address = models.CharField(max_length=42, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_superadmin = models.BooleanField(default=False)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "users"

    def __str__(self):
        return self.username


class ApiKey(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(GaxtronUser, on_delete=models.DO_NOTHING, db_column="user_id")
    key_hash = models.CharField(max_length=255)
    key_prefix = models.CharField(max_length=12)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "api_keys"

    def __str__(self):
        return f"{self.key_prefix}..."


class Payment(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(GaxtronUser, on_delete=models.DO_NOTHING, db_column="user_id")
    amount = models.DecimalField(max_digits=36, decimal_places=18)
    chain = models.CharField(max_length=10, default="ETH")
    currency = models.CharField(max_length=10)
    status = models.CharField(max_length=20)
    wallet_address = models.CharField(max_length=128)
    callback_url = models.TextField()
    tx_hash = models.CharField(max_length=128, null=True, blank=True)
    created_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "payments"
        ordering = ["-created_at"]


class Transaction(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(GaxtronUser, on_delete=models.DO_NOTHING, db_column="user_id")
    payment = models.ForeignKey(
        Payment, on_delete=models.DO_NOTHING, db_column="payment_id", null=True, blank=True
    )
    tx_hash = models.CharField(max_length=128)
    amount = models.DecimalField(max_digits=36, decimal_places=18)
    chain = models.CharField(max_length=10, default="ETH")
    currency = models.CharField(max_length=10)
    from_address = models.CharField(max_length=128)
    to_address = models.CharField(max_length=128)
    status = models.CharField(max_length=20)
    confirmations = models.IntegerField(default=0)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "transactions"
        ordering = ["-created_at"]


class WebhookLog(models.Model):
    id = models.AutoField(primary_key=True)
    payment = models.ForeignKey(Payment, on_delete=models.DO_NOTHING, db_column="payment_id")
    event_id = models.CharField(max_length=64)
    callback_url = models.TextField()
    payload = models.TextField()
    status = models.CharField(max_length=20)
    response_code = models.IntegerField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField()
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "webhook_logs"
        ordering = ["-created_at"]
