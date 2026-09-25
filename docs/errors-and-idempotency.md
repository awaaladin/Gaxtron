# Errors & idempotency

## Error format

```json
{ "error": { "code": "insufficient_funds", "message": "Insufficient available balance" } }
```

Validation failures (`400 invalid_request`) also include `fields` with the per-field problems.

| HTTP | `code` | Meaning |
|---|---|---|
| 400 | `invalid_request` | Malformed or invalid input (bad amount, bad address, missing field) |
| 401 | `unauthorized` | Missing, invalid or revoked API key |
| 402 | `insufficient_funds` | The user's available balance is too low |
| 404 | `not_found` | Unknown id — or it belongs to another platform |
| 409 | `invalid_state` | The action isn't allowed in the object's current state (e.g. refund after release) |
| 409 | `conflict` | Same `reference` / `Idempotency-Key` reused with different details |
| 422 | `limit_exceeded` | A withdrawal limit was hit |
| 429 | `rate_limited` | Slow down; retry after a short pause |

Anything `5xx` is our fault and safe to retry **with the same idempotency key / reference**.

## Idempotency

Networks fail. To retry safely without paying twice:

| Endpoint | How it is made idempotent |
|---|---|
| `POST /v1/escrows` | Automatically, by `reference` (your order id) |
| `POST /v1/escrows/{id}/release` `/refund` `/dispute` | Automatically, by the escrow's state |
| `POST /v1/transfers`, `POST /v1/withdrawals`, `POST /v1/sandbox/credit` | Send an `Idempotency-Key` header (1–128 chars, unique per logical request, e.g. a UUID) |

Repeating a request with the same key and the same parameters returns the original result (`200`
instead of `201`) and changes nothing. Reusing a key with **different** parameters returns
`409 conflict` — that is always a bug in the caller, and Gaxtron refuses rather than guessing.

Recommended client behaviour: generate the key once per user action, persist it, and reuse it for every
retry of that action.

## Amounts

Strings with at most 6 decimals. `"0"`, negatives, more than 6 decimals, `NaN` and values above
1,000,000,000 are rejected with `400`.
