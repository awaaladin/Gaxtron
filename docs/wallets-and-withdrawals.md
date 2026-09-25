# Wallets, transfers & withdrawals

## Users and balances

`POST /v1/users` with `{"external_id": "alice", "email": "alice@example.com"}` creates (or returns) a user.
`GET /v1/users/{external_id}` returns the user with their balance:

```json
{ "id": "alice", "email": "alice@example.com", "created_at": "...",
  "balance": { "currency": "USDT", "available": "60.000000", "held_as_buyer": "40.000000",
               "incoming_as_seller": "0.000000", "pending_withdrawals": "0.000000" } }
```

| Field | Meaning |
|---|---|
| `available` | Spendable right now |
| `held_as_buyer` | Locked in open escrows the user funded |
| `incoming_as_seller` | Held in open escrows that will pay this user on release |
| `pending_withdrawals` | Reserved for withdrawals that have not finished |

`GET /v1/users/{external_id}/balance` returns just the balance. `GET /v1/users/{external_id}/transactions`
lists ledger entries (newest first, signed amounts: positive = credit, negative = debit).

## Funding a balance

- **Sandbox:** `POST /v1/sandbox/credit` with `{"user": "alice", "amount": "100"}` mints fake test USDT.
  This endpoint only exists on test-network deployments and returns `404` everywhere else.
- **Production:** users deposit real USDT (TRC-20) on-chain and Gaxtron credits their balance once the
  transfer is irreversible. *Per-user deposit addresses are being finished and are not yet in this API.*

## Transfers

`POST /v1/transfers` moves balance between two of your users instantly and for free:

```json
{ "from_user": "alice", "to_user": "bob", "amount": "10", "description": "Splitting lunch" }
```

Send an `Idempotency-Key` header so a network retry cannot pay twice. Insufficient funds → `402`.

## Withdrawals (cash out to a wallet)

`POST /v1/withdrawals`

```json
{ "user": "bob", "amount": "25", "destination": "TXYZopYRdj2D9XRtbG411XZZ3kM5VkAeBf" }
```

`destination` must be a valid TRON address (starts with `T`). The amount is reserved from `available`
immediately.

| Status | Meaning |
|---|---|
| `pending_approval` | Waiting for a Gaxtron operator (all withdrawals start here unless auto-approval is enabled) |
| `approved` | Cleared; queued to send |
| `broadcast` | Sent to the network, awaiting confirmation (`tx_hash` is set) |
| `completed` | Confirmed on-chain |
| `failed` | Could not be sent; **the user is refunded in full** |
| `cancelled` | You cancelled it before it was sent; the user is refunded |

`POST /v1/withdrawals/{id}/cancel` works only before `broadcast`. `GET /v1/withdrawals/{id}` and
`GET /v1/withdrawals?user=bob&status=completed` read them back.

`net_amount = amount − fee` is what arrives at the destination. Minimum amount, per-user and per-platform
daily limits apply; hitting one returns `422 limit_exceeded`. Withdrawals are irreversible once broadcast —
show users the destination address and ask them to confirm.

## Cashing out to Naira / USD

Fiat off-ramp is provided through a licensed partner and is **not part of this API yet**. Until then,
users withdraw USDT to their own wallet or exchange account and convert there.
