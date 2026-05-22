from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User

from merchants.forms import MerchantRegistrationForm
from merchants.utils import ensure_gaxtron_merchant
from django.db.models import Count, Sum
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from merchants.models import ApiKey, GaxtronUser, Payment, Transaction, WebhookLog


def _get_merchant_user(request):
    """Map Django auth user to Gaxtron merchant by email."""
    return GaxtronUser.objects.filter(email=request.user.email, is_active=True).first()


@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.method == "POST":
        form = MerchantRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            ensure_gaxtron_merchant(
                email=form.cleaned_data["email"],
                username=form.cleaned_data["username"],
                password=form.cleaned_data["password1"],
            )
            login(request, user)
            messages.success(request, "Merchant account created. API keys: use FastAPI /api-keys or dashboard.")
            return redirect("dashboard")
    else:
        form = MerchantRegistrationForm()
    return render(request, "merchants/register.html", {"form": form})


@login_required
def dashboard_view(request):
    merchant = _get_merchant_user(request)
    stats = {
        "total_payments": 0,
        "successful": 0,
        "failed": 0,
        "pending": 0,
        "revenue": Decimal("0"),
    }
    recent_payments = []

    if merchant:
        payments = Payment.objects.filter(user_id=merchant.id)
        stats["total_payments"] = payments.count()
        stats["successful"] = payments.filter(status="confirmed").count()
        stats["failed"] = payments.filter(status="failed").count()
        stats["pending"] = payments.filter(status="pending").count()
        revenue = payments.filter(status="confirmed").aggregate(total=Sum("amount"))
        stats["revenue"] = revenue["total"] or Decimal("0")
        recent_payments = payments[:10]

    return render(
        request,
        "merchants/dashboard.html",
        {"stats": stats, "recent_payments": recent_payments, "merchant": merchant},
    )


@login_required
def transactions_view(request):
    merchant = _get_merchant_user(request)
    txs = []
    status_filter = request.GET.get("status", "")
    date_from = request.GET.get("from", "")

    if merchant:
        txs = Transaction.objects.filter(user_id=merchant.id)
        if status_filter:
            txs = txs.filter(status=status_filter)
        if date_from:
            txs = txs.filter(created_at__gte=date_from)

    return render(
        request,
        "merchants/transactions.html",
        {"transactions": txs, "status_filter": status_filter, "date_from": date_from},
    )


@login_required
def api_keys_view(request):
    merchant = _get_merchant_user(request)
    keys = ApiKey.objects.filter(user_id=merchant.id) if merchant else []
    return render(
        request,
        "merchants/api_keys.html",
        {"api_keys": keys, "fastapi_url": "http://localhost:8000"},
    )


@login_required
def webhooks_view(request):
    merchant = _get_merchant_user(request)
    logs = []
    if merchant:
        payment_ids = Payment.objects.filter(user_id=merchant.id).values_list("id", flat=True)
        logs = WebhookLog.objects.filter(payment_id__in=payment_ids)[:50]
    return render(request, "merchants/webhooks.html", {"webhook_logs": logs})


@user_passes_test(lambda u: u.is_superuser)
def admin_overview(request):
    users = GaxtronUser.objects.all()
    total_tx = Transaction.objects.count()
    return render(
        request,
        "merchants/admin_overview.html",
        {"users": users, "total_transactions": total_tx},
    )


def logout_view(request):
    logout(request)
    return redirect("login")
