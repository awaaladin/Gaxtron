"""Operator console. Ledger history is read-only here; the only writes are withdrawal approvals."""
from django.contrib import admin, messages

from . import services
from .models import Account, EndUser, Entry, Escrow, LedgerTransaction, PlatformConfig, WebhookEvent, Withdrawal


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class EntryInline(admin.TabularInline):
    model = Entry
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Account)
class AccountAdmin(ReadOnlyAdmin):
    list_display = ("id", "platform", "kind", "end_user", "currency", "balance")
    list_filter = ("kind",)


@admin.register(LedgerTransaction)
class LedgerTransactionAdmin(ReadOnlyAdmin):
    list_display = ("id", "platform", "kind", "reference", "created_at")
    list_filter = ("kind",)
    inlines = [EntryInline]


@admin.register(Escrow)
class EscrowAdmin(ReadOnlyAdmin):
    list_display = ("public_id", "platform", "reference", "buyer", "seller", "amount", "status", "created_at")
    list_filter = ("status",)


@admin.register(EndUser)
class EndUserAdmin(ReadOnlyAdmin):
    list_display = ("id", "platform", "external_id", "created_at")


@admin.register(WebhookEvent)
class WebhookEventAdmin(ReadOnlyAdmin):
    list_display = ("event_id", "platform", "type", "status", "attempts", "created_at")
    list_filter = ("status", "type")


@admin.register(PlatformConfig)
class PlatformConfigAdmin(admin.ModelAdmin):
    list_display = ("platform", "webhook_url", "fee_bps")
    exclude = ("webhook_secret_encrypted",)


@admin.register(Withdrawal)
class WithdrawalAdmin(ReadOnlyAdmin):
    list_display = ("public_id", "platform", "end_user", "amount", "destination", "status", "approved_by", "created_at")
    list_filter = ("status",)
    actions = ["approve_selected", "fail_selected"]

    @admin.action(description="Approve selected withdrawals (funds will be sent on-chain)")
    def approve_selected(self, request, queryset):
        for withdrawal in queryset:
            try:
                services.approve_withdrawal(withdrawal.public_id, approver=request.user.username)
            except services.LedgerError as exc:
                self.message_user(request, f"{withdrawal.public_id}: {exc.message}", level=messages.ERROR)

    @admin.action(description="Reject selected withdrawals (refund the user)")
    def fail_selected(self, request, queryset):
        for withdrawal in queryset:
            try:
                services.fail_withdrawal(withdrawal.public_id, f"Rejected by {request.user.username}")
            except services.LedgerError as exc:
                self.message_user(request, f"{withdrawal.public_id}: {exc.message}", level=messages.ERROR)
