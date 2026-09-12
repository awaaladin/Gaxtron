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
    return render(
        request,
        "merchants/dashboard.html",
        {"stats": stats, "recent_payments": payments[:10]},
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
        {"transactions": txs, "status_filter": status_filter, "date_from": date_from},
    )


@login_required
def api_keys_view(request):
    keys = ApiKey.objects.filter(user=request.user)
    return render(request, "merchants/api_keys.html", {"api_keys": keys})


@login_required
def markets_view(request):
    return render(request, "merchants/markets.html")


@login_required
def profile_view(request):
    return render(request, "merchants/profile.html")


@login_required
def webhooks_view(request):
    payment_ids = Payment.objects.filter(user=request.user).values_list("id", flat=True)
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


def pay_view(request, payment_ref: str):
    """Hosted checkout UI — polls this same Django app's /payment/{ref} for status."""
    return render(request, "merchants/pay.html", {"payment_ref": payment_ref})
