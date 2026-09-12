"""REST API routes — paths match GaX/app/api/routers/{auth,api_keys,payments,checkout}.py exactly."""
from django.urls import path

from . import api_views, cron_views, markets_views, payment_views

urlpatterns = [
    path("auth/register", api_views.RegisterView.as_view(), name="api_register"),
    path("auth/login", api_views.LoginView.as_view(), name="api_login"),
    path("auth/wallet/nonce", api_views.WalletNonceView.as_view(), name="api_wallet_nonce"),
    path("auth/wallet/verify", api_views.WalletVerifyView.as_view(), name="api_wallet_verify"),
    path("auth/me", api_views.MeView.as_view(), name="api_me"),
    path("api-keys", api_views.ApiKeysView.as_view(), name="api_keys"),
    path("api-keys/<int:key_id>", api_views.ApiKeyDetailView.as_view(), name="api_key_detail"),
    path("api-keys/<int:key_id>/regenerate", api_views.ApiKeyRegenerateView.as_view(), name="api_key_regenerate"),

    path("create-payment", payment_views.CreatePaymentView.as_view(), name="create_payment"),
    path("payments", payment_views.ListPaymentsView.as_view(), name="list_payments"),
    path("payment/<int:payment_id>/merchant", payment_views.PaymentMerchantDetailView.as_view(), name="payment_merchant_detail"),
    path("verify-payment/<int:payment_id>", payment_views.VerifyPaymentView.as_view(), name="verify_payment"),

    path("payment/<str:payment_ref>", payment_views.PublicPaymentStatusView.as_view(), name="public_payment_status"),
    path("checkout/<str:payment_ref>", payment_views.checkout_redirect, name="checkout_redirect"),
    path("link/<str:payment_ref>", payment_views.payment_link_redirect, name="payment_link_redirect"),
    path("pay", payment_views.pay_query_redirect, name="pay_query_redirect"),

    path("markets/prices", markets_views.MarketPricesView.as_view(), name="market_prices"),
    path("markets/chart/<str:coin_id>", markets_views.MarketChartView.as_view(), name="market_chart"),

    path("api/cron/check-payments", cron_views.CronCheckPaymentsView.as_view(), name="cron_check_payments"),
]
