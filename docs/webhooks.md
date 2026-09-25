# Webhooks

Gaxtron calls your server when something changes, so you don't have to poll.

## Setup

```bash
curl -X PUT $GAX/webhook-config -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"url": "https://api.yourapp.com/gaxtron/webhook"}'
```

The response contains your `signing_secret` (`whsec_…`). The URL must be public HTTPS — private,
loopback and cloud-metadata addresses are rejected. Rotate the secret any time with
`POST /v1/webhook-config/rotate-secret` (the old one stops working immediately).
`GET /v1/webhook-events` shows recent events with their delivery status and response code.

## Events

| Type | When |
|---|---|
| `escrow.created` / `escrow.released` / `escrow.refunded` / `escrow.disputed` | Escrow state changes (`data` is the escrow object) |
| `deposit.credited` | A user's balance was credited (`data`: `user`, `amount`, `tx_id`) |
| `transfer.created` | An instant transfer completed |
| `withdrawal.created` / `withdrawal.completed` / `withdrawal.failed` / `withdrawal.cancelled` | Withdrawal changes (`data` is the withdrawal object) |

```json
{ "id": "evt_9c1f…", "type": "escrow.released", "created": 1790000000, "data": { "id": "esc_3f9a…", "status": "released" } }
```

## Verify every request

Each delivery carries `X-Gaxtron-Signature: t=<unix seconds>,v1=<hex>` where
`v1 = HMAC_SHA256(signing_secret, "<t>.<raw request body>")`. Verify against the **raw bytes** of the body
(before JSON parsing) and reject old timestamps to stop replays.

```python
import hashlib, hmac, time

def verify(secret: str, header: str, raw_body: bytes, tolerance: int = 300) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    t = int(parts["t"])
    if abs(time.time() - t) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])
```

```js
const crypto = require("crypto");
function verify(secret, header, rawBody, tolerance = 300) {
  const parts = Object.fromEntries(header.split(",").map((p) => p.split("=")));
  if (Math.abs(Date.now() / 1000 - Number(parts.t)) > tolerance) return false;
  const expected = crypto.createHmac("sha256", secret).update(`${parts.t}.${rawBody}`).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(parts.v1));
}
```

## Delivery guarantees

- Respond `2xx` quickly (under 10 seconds). Anything else — or a timeout — is retried with exponential
  backoff (30 s, 1 min, 2 min, …) up to 5 attempts.
- Delivery is **at-least-once**: deduplicate on the event `id`, and make your handler idempotent.
- Events are not guaranteed to arrive in order. Use the object in `data`, or re-fetch it, rather than
  assuming the previous event was processed first.
- Redirects are not followed.
