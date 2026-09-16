"""One-shot check of a payment's status + its webhook log. Prints a single line, exit 0 if
confirmed+delivered, exit 1 otherwise (so a poll loop can watch for exit 0)."""
import os
import sys

import django

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from merchants.models import Payment, WebhookLog  # noqa: E402

PAYMENT_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 4


def main() -> None:
    payment = Payment.objects.filter(id=PAYMENT_ID).first()
    if not payment:
        print(f"payment={PAYMENT_ID} not found")
        sys.exit(1)

    wh = WebhookLog.objects.filter(payment_id=PAYMENT_ID).first()
    wh_status = f"{wh.status} code={wh.response_code} attempts={wh.attempts}" if wh else "no webhook_log row yet"

    print(
        f"payment={PAYMENT_ID} status={payment.status} tx_hash={payment.tx_hash} "
        f"confirmations={payment.confirmations} webhook=[{wh_status}]"
    )

    if payment.status == "confirmed" and wh and wh.status == "delivered":
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
