from django.contrib import admin

from merchants.models import ApiKey, GaxtronUser, Payment, Transaction, WebhookLog


@admin.register(GaxtronUser)
class GaxtronUserAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "email", "is_active", "is_superadmin", "created_at")
    list_filter = ("is_active", "is_superadmin")
    search_fields = ("username", "email")
    actions = ["suspend_accounts", "activate_accounts"]

    @admin.action(description="Suspend selected accounts")
    def suspend_accounts(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description="Activate selected accounts")
    def activate_accounts(self, request, queryset):
        queryset.update(is_active=True)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "amount", "currency", "status", "wallet_address", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("wallet_address", "tx_hash")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "tx_hash", "amount", "currency", "status", "confirmations", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("tx_hash", "to_address")


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "key_prefix", "name", "is_active", "last_used_at")
    list_filter = ("is_active",)


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ("id", "payment", "status", "response_code", "attempts", "created_at", "delivered_at")
    list_filter = ("status",)
