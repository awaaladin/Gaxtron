from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from . import views

urlpatterns = [
    path("users", views.UsersView.as_view()),
    path("users/<str:external_id>", views.UserDetailView.as_view()),
    path("users/<str:external_id>/balance", views.UserBalanceView.as_view()),
    path("users/<str:external_id>/transactions", views.UserTransactionsView.as_view()),
    path("users/<str:external_id>/deposit-address", views.UserDepositAddressView.as_view()),
    path("transfers", views.TransfersView.as_view()),
    path("sandbox/credit", views.SandboxCreditView.as_view()),
    path("escrows", views.EscrowsView.as_view()),
    path("escrows/<str:escrow_id>", views.EscrowDetailView.as_view()),
    path("escrows/<str:escrow_id>/release", views.EscrowReleaseView.as_view()),
    path("escrows/<str:escrow_id>/refund", views.EscrowRefundView.as_view()),
    path("escrows/<str:escrow_id>/dispute", views.EscrowDisputeView.as_view()),
    path("payments", views.PaymentsView.as_view()),
    path("payments/<str:payment_id>", views.PaymentDetailView.as_view()),
    path("commission-config", views.CommissionConfigView.as_view()),
    path("withdrawals", views.WithdrawalsView.as_view()),
    path("withdrawals/<str:withdrawal_id>", views.WithdrawalDetailView.as_view()),
    path("withdrawals/<str:withdrawal_id>/cancel", views.WithdrawalCancelView.as_view()),
    path("webhook-config", views.WebhookConfigView.as_view()),
    path("webhook-config/rotate-secret", views.WebhookSecretRotateView.as_view()),
    path("webhook-events", views.WebhookEventsView.as_view()),
    path("openapi.json", SpectacularAPIView.as_view(), name="ledger_schema"),
    path("docs", SpectacularSwaggerView.as_view(url_name="ledger_schema")),
]
