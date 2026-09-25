# Escrow

Escrow protects both sides of a marketplace sale. The buyer's money leaves their spendable balance the
moment they click **Buy**, but the seller only receives it when *you* release it.

```
        hold                 release
buyer ─────────► ESCROW ─────────────► seller   (minus your Gaxtron fee)
                   │  refund
                   └─────────────────► buyer    (in full)
```

## States

| Status | Meaning | Next |
|---|---|---|
| `held` | Funds locked | `released`, `refunded`, `disputed` |
| `disputed` | Flagged for review; funds still locked | `released`, `refunded` |
| `released` | Seller paid — **final** | — |
| `refunded` | Buyer repaid — **final** | — |

Every action is idempotent: repeating a `release` on a released escrow returns the same escrow with
`200`; trying to `refund` it returns `409 invalid_state`. Money can never move twice.

## The marketplace flow

| In your app | Call |
|---|---|
| Buyer clicks **Buy** | `POST /v1/escrows` |
| Buyer confirms receipt, or your auto-release timer fires | `POST /v1/escrows/{id}/release` |
| Order cancelled / seller failed to ship | `POST /v1/escrows/{id}/refund` |
| Buyer opens a dispute | `POST /v1/escrows/{id}/dispute`, then release or refund after your review |

Your order state machine stays in charge of *when*; Gaxtron only guarantees the money is where you say it is.

## Create (hold)

`POST /v1/escrows`

```json
{ "reference": "order-1001", "buyer": "alice", "seller": "bob", "amount": "40.00",
  "metadata": { "listing": "iphone-13" } }
```

- `reference` is your order id. It is unique per platform, so a retried request cannot double-charge:
  the same reference with the same details returns the existing escrow (`200`); different details
  return `409 conflict`.
- The buyer must already exist and have enough `available` balance, otherwise `402 insufficient_funds`
  and nothing is created. The seller is created automatically if new.
- `metadata` is an optional object (under 2,000 characters) returned on every read.

Response `201`:

```json
{ "id": "esc_3f9a…", "reference": "order-1001", "status": "held", "buyer": "alice", "seller": "bob",
  "amount": "40.000000", "fee": "1.000000", "currency": "USDT", "metadata": {"listing": "iphone-13"},
  "dispute_reason": "", "created_at": "2026-09-25T10:00:00Z", "resolved_at": null }
```

`fee` is fixed at creation (your platform's `fee_bps`, default 0). On release the seller receives
`amount − fee`. On refund the buyer receives the full `amount`.

## Other calls

| Call | Purpose |
|---|---|
| `GET /v1/escrows/{id}` | Fetch one |
| `GET /v1/escrows?status=held&buyer=alice&seller=bob&reference=order-1001` | List / filter |
| `POST /v1/escrows/{id}/release` | Pay the seller |
| `POST /v1/escrows/{id}/refund` | Repay the buyer |
| `POST /v1/escrows/{id}/dispute` with `{"reason": "..."}` | Mark disputed |

Each state change fires a webhook (`escrow.created`, `escrow.released`, `escrow.refunded`, `escrow.disputed`)
— see [webhooks](webhooks.md).

## Integration checklist

- Store the escrow `id` on your order; it is what you release or refund.
- Call `release`/`refund` from your server only — never expose your API key to browsers or apps.
- Treat `409 invalid_state` on a repeat as "already done", not as a failure.
- Reconcile on webhooks *and* by reading the escrow; webhooks are delivered at-least-once.
