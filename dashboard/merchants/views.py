from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from merchants.forms import MerchantRegistrationForm
from merchants.models import ApiKey, GaxtronUser, Payment, Transaction, WebhookLog


def landing_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    return render(request, "merchants/index.html")


@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.method == "POST":
        form = MerchantRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Merchant account created.")
            return redirect("dashboard")
    else:
        form = MerchantRegistrationForm()
    return render(request, "merchants/register.html", {"form": form})


@login_required
def dashboard_view(request):
    payments = Payment.objects.filter(user=request.user)
    stats = {
        "total_payments": payments.count(),
        "successful": payments.filter(status="confirmed").count(),
        "failed": payments.filter(status="failed").count(),
        "pending": payments.filter(status="pending").count(),
        "revenue": payments.filter(status="confirmed").aggregate(total=Sum("amount"))["total"] or Decimal("0"),
    }
    latest_key = ApiKey.objects.filter(user=request.user, is_active=True).order_by("-created_at").first()
    return render(
        request,
        "merchants/dashboard.html",
        {"stats": stats, "recent_payments": payments[:6], "latest_key": latest_key, "active_nav": "Dashboard"},
    )


@login_required
def payments_view(request):
    from merchants.payment_service import PaymentService

    created = None
    error = None
    if request.method == "POST":
        amount = request.POST.get("amount", "").strip()
        callback_url = request.POST.get("callback_url", "").strip()
        try:
            created = PaymentService.create_payment(user_id=request.user.id, amount=amount, callback_url=callback_url)
        except ValueError as e:
            error = str(e)
        except Exception:
            error = "Failed to create payment. Check the amount and callback URL."

    payments = Payment.objects.filter(user=request.user)
    return render(
        request,
        "merchants/payments.html",
        {
            "payments": payments,
            "created": created,
            "created_url": PaymentService.build_payment_url(created) if created else None,
            "error": error,
            "active_nav": "Payments",
        },
    )


@login_required
def transactions_view(request):
    status_filter = request.GET.get("status", "")
    date_from = request.GET.get("from", "")

    txs = Transaction.objects.filter(user=request.user)
    if status_filter:
        txs = txs.filter(status=status_filter)
    if date_from:
        txs = txs.filter(created_at__gte=date_from)

    return render(
        request,
        "merchants/transactions.html",
        {"transactions": txs, "status_filter": status_filter, "date_from": date_from, "active_nav": "Transactions"},
    )


@login_required
@require_http_methods(["GET", "POST"])
def api_keys_view(request):
    from django.conf import settings

    from . import security

    created_key = None
    error = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            active_count = ApiKey.objects.filter(user=request.user, is_active=True).count()
            if active_count >= settings.MAX_API_KEYS_PER_USER:
                error = f"Maximum {settings.MAX_API_KEYS_PER_USER} active API keys allowed."
            else:
                name = request.POST.get("name", "").strip() or "default"
                raw_key = security.generate_api_key()
                ApiKey.objects.create(
                    user=request.user, key_hash=security.hash_api_key(raw_key), key_prefix=raw_key[:12], name=name
                )
                created_key = raw_key
        elif action == "revoke":
            ApiKey.objects.filter(id=request.POST.get("key_id"), user=request.user).update(is_active=False)

    keys = ApiKey.objects.filter(user=request.user).order_by("-created_at")
    return render(
        request,
        "merchants/api_keys.html",
        {"api_keys": keys, "created_key": created_key, "error": error, "active_nav": "API keys"},
    )


@login_required
def markets_view(request):
    return render(request, "merchants/markets.html", {"active_nav": "Markets"})


@login_required
def agent_view(request):
    return render(request, "merchants/agent.html", {"active_nav": "Agent"})


@login_required
def profile_view(request):
    return render(request, "merchants/profile.html", {"active_nav": "Profile"})


@login_required
def webhooks_view(request):
    payment_ids = Payment.objects.filter(user=request.user).values_list("id", flat=True)
    logs = WebhookLog.objects.filter(payment_id__in=payment_ids)[:50]
    return render(request, "merchants/webhooks.html", {"webhook_logs": logs, "active_nav": "Webhooks"})


@user_passes_test(lambda u: u.is_superuser)
def admin_overview(request):
    users = GaxtronUser.objects.all()
    total_tx = Transaction.objects.count()
    return render(
        request,
        "merchants/admin_overview.html",
        {"users": users, "total_transactions": total_tx, "active_nav": "Admin"},
    )


def logout_view(request):
    logout(request)
    return redirect("login")


def pay_view(request, payment_ref: str):
    """Hosted checkout UI — polls this same Django app's /payment/{ref} for status."""
    return render(request, "merchants/pay.html", {"payment_ref": payment_ref})
