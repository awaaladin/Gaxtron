# Deploy Gaxtron on Vercel (Cron + external DB)

## How confirmation works

| Trigger | Frequency | Purpose |
|---------|-----------|---------|
| **Vercel Cron** | Every **1 minute** (fastest on Hobby) | Scan all pending payments + deliver webhooks |
| **Checkout poll** | Every **3 seconds** | `GET /payment/{id}` re-checks Sepolia for that payment |

Vercel Cron **cannot** run every few seconds on Hobby. Checkout polling gives near real-time UX while the customer has the page open.

## 1. External services (free tier)

- **Neon** or **Supabase** — Postgres → `DATABASE_URL`
- **Upstash** — Redis → `REDIS_URL` (optional; cron + DB still work without it)
- **Alchemy/Infura** — `BLOCKCHAIN_RPC_URL` (Sepolia)

## 2. Vercel environment variables

```
DATABASE_URL=postgresql://...
REDIS_URL=rediss://...          # optional
BLOCKCHAIN_RPC_URL=https://eth-sepolia.g.alchemy.com/v2/KEY
ENABLED_CHAINS=ETH
PUBLIC_BASE_URL=https://your-app.vercel.app
CRON_SECRET=<openssl rand -hex 32>
SECRET_KEY=...
WEBHOOK_SECRET=...
WALLET_ENCRYPTION_KEY=...
ENV=production
DEBUG=False
```

`PUBLIC_BASE_URL` must match your Vercel URL (payment links + webhooks).

## 3. Deploy

1. Connect GitHub repo to Vercel.
2. Root directory: **repository root** (where `vercel.json` lives).
3. Deploy — `api/index.py` serves the FastAPI app.
4. `vercel.json` registers cron → `GET /api/cron/check-payments` every minute.

## 4. Verify cron

```bash
curl -H "Authorization: Bearer YOUR_CRON_SECRET" \
  https://your-app.vercel.app/api/cron/check-payments
```

Expected: `{"ok":true,"payments_checked":0,...}`

Vercel also invokes this automatically when `CRON_SECRET` is set.

## 5. Test payment flow

1. Register on `https://your-app.vercel.app/register.html`
2. Create payment → open checkout link
3. Send Sepolia ETH
4. Checkout updates within ~3s (poll); cron catches anything if the tab is closed

## Local dev (no cron)

```powershell
.\scripts\start_eth_product.ps1
# optional manual cron:
curl -H "Authorization: Bearer dev-cron-secret" http://127.0.0.1:8002/api/cron/check-payments
```

Set `CRON_SECRET=dev-cron-secret` in `.env` for local testing.
