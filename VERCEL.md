# Deploy Gaxtron on Vercel (Cron + external DB)

## How confirmation works

| Trigger | Frequency | Purpose |
|---------|-----------|---------|
| **Vercel Cron** | **Once per day** on Hobby (`0 0 * * *`); Pro = every minute | Backup scan for pending payments |
| **Checkout poll** | Every **3 seconds** | `GET /payment/{id}` re-checks Sepolia for that payment |

Vercel Cron **cannot** run every few seconds on Hobby. Checkout polling gives near real-time UX while the customer has the page open.

## 1. External services (free tier)

### Postgres `DATABASE_URL` (use Neon — not local Docker)

1. Go to https://neon.tech → Sign up (free)
2. Create project → region closest to you
3. Copy **Connection string** (looks like):
   ```
   postgresql://neondb_owner:PASSWORD@ep-xxxx.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
4. Paste into Vercel as `DATABASE_URL`

Local Docker URL (`127.0.0.1:5433`) **only works on your PC**, not on Vercel.

### Blockchain RPC `BLOCKCHAIN_RPC_URL` (Sepolia)

**Recommended — Alchemy (free):**

1. https://dashboard.alchemy.com → Sign up
2. **Create App** → Chain: **Ethereum**, Network: **Ethereum Sepolia**
3. Copy **HTTPS** URL:
   ```
   https://eth-sepolia.g.alchemy.com/v2/YOUR_API_KEY
   ```
4. Paste into Vercel as `BLOCKCHAIN_RPC_URL`

**Alternatives:** [Infura](https://infura.io) (Sepolia endpoint) or public `https://rpc.sepolia.org` (slow/unreliable for production).

### Redis (optional)

- **Upstash** https://upstash.com → Redis → copy `REDIS_URL`

### `CRON_SECRET` (generate in terminal)

PowerShell or Git Bash:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste result into Vercel as `CRON_SECRET` (no quotes). Vercel sends it as `Authorization: Bearer <value>` when cron runs.

Also generate (same command, run 3 times or use):

```powershell
python -c "import secrets; print('SECRET_KEY='+secrets.token_hex(32))"
python -c "import secrets; print('WEBHOOK_SECRET='+secrets.token_hex(32))"
python -c "import secrets; print('WALLET_ENCRYPTION_KEY='+secrets.token_hex(32))"
```

Each must be **at least 32 characters**.

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
