# Gaxtron API

Gaxtron gives your platform custodial **USDT (TRC-20)** wallets, **escrow**, instant transfers and
withdrawals behind one REST API — the "Stripe for crypto" for marketplaces. Your users never sign a
transaction to buy something: a purchase is an instant ledger movement, and real USDT only moves on
the blockchain when someone deposits or withdraws.

| Guide | What it covers |
|---|---|
| [Escrow](escrow.md) | Hold, release, refund and dispute — the marketplace buy flow |
| [Wallets, transfers & withdrawals](wallets-and-withdrawals.md) | User balances, instant transfers, cashing out to a wallet |
| [Webhooks](webhooks.md) | Event list, signature verification, retries |
| [Errors & idempotency](errors-and-idempotency.md) | Error codes, safe retries, rate limits |
| [Security & going live](security.md) | Key handling, guarantees, the mainnet checklist |

Interactive reference (try requests in the browser): **`/v1/docs`** · machine-readable schema: **`/v1/openapi.json`**.

## Concepts

- **Platform** — you. One API key = one platform. Everything you create is invisible to other platforms.
- **User** — one of *your* end users, identified by *your own* `external_id` (e.g. your user id). Users are
  created on first use; you never store Gaxtron ids.
- **Balance** — a user's USDT held by Gaxtron. `available` is spendable; funds locked in escrow or
  reserved for a withdrawal are reported separately.
- **Escrow** — funds moved out of the buyer's balance and held until *you* tell Gaxtron to release them to
  the seller or refund the buyer. Gaxtron never decides who is right; your order logic does.

## Quickstart (sandbox)

Sandbox runs on a TRON test network — no real money. Base URL: `https://gaxtron.vercel.app/v1`.

```bash
export GAX=https://gaxtron.vercel.app/v1
export KEY=gax_your_api_key

# 1. Give a test user some fake USDT (sandbox only — this endpoint does not exist in production)
curl -s $GAX/sandbox/credit -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"user":"alice","amount":"100"}'

# 2. Alice buys from Bob: 40 USDT moves into escrow
curl -s $GAX/escrows -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"reference":"order-1001","buyer":"alice","seller":"bob","amount":"40"}'

# 3. Goods delivered — release the escrow to Bob
curl -s -X POST $GAX/escrows/esc_XXXX/release -H "X-API-Key: $KEY"

# 4. Bob's balance
curl -s $GAX/users/bob/balance -H "X-API-Key: $KEY"
```

## Conventions

- **Auth:** send your key in the `X-API-Key` header on every request. Keep it server-side only.
- **JSON only.** Paths have no trailing slash.
- **Amounts are strings** with up to 6 decimals (`"12.500000"`). Never use floats. Currency is always `USDT`.
- **Ids:** escrows `esc_…`, withdrawals `wd_…`, webhook events `evt_…`. Users use *your* `external_id`.
- **Lists** return `{"data": [...], "has_more": bool}`, newest first. Page with `?limit=` (max 100) and
  `?starting_after=<id of the last item>`.
- **Errors** are always `{"error": {"code": "...", "message": "..."}}` — see [errors](errors-and-idempotency.md).
- **Rate limit:** 100 requests/minute per endpoint per key (withdrawals: 10/minute). Exceeding it returns `429`.
