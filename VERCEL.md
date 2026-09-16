# Deploy Gaxtron on Vercel (Cron + external DB)

## How confirmation works

| Trigger | Frequency | Purpose |
|---------|-----------|---------|
| **Render worker** | **Continuous** — polls every 5s | `python manage.py run_listener` running as a persistent background worker; detects deposits with no browser tab open |
| **Vercel Cron** | **Once per day** on Hobby (`0 0 * * *`); Pro = every minute | Backup scan for pending payments if the worker is ever down |
| **Checkout poll** | Every **3 seconds** | `GET /payment/{id}` re-checks Sepolia for that payment while the customer has the page open |

Vercel serverless functions can't run a long-lived process, so the listener itself doesn't live on Vercel — see **Section 6** for deploying it to Render. Vercel Cron and checkout polling are both fallbacks/UX sugar on top of the worker, not a replacement for it.

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
4. Checkout updates within ~3s (poll); the Render worker (or cron) catches anything if the tab is closed

## 6. Persistent worker on Render

Vercel can only run request-scoped serverless functions, so the actual listener —
`python manage.py run_listener` — runs continuously on Render instead, using the same
`Dockerfile.dashboard` as local Docker Compose's `worker` service and the same Supabase
`DATABASE_URL` as the Vercel web app. Render's **Background Worker** service type is
built for exactly this: no public port, auto-restarts if the process dies.

**Deploy via Blueprint (`render.yaml`, already in the repo root):**

1. https://dashboard.render.com → **New** → **Blueprint**
2. Connect this GitHub repo → Render detects `render.yaml` and proposes the
   `gaxtron-listener` worker service
3. Fill in the env vars Render prompts for (anything marked `sync: false` in
   `render.yaml`) — use the **same values** as your Vercel environment variables:
   ```
   DATABASE_URL          same Supabase URL as Vercel
   REDIS_URL             same as Vercel (optional)
   SECRET_KEY            same as Vercel
   DJANGO_SECRET_KEY     same as Vercel
   WEBHOOK_SECRET        same as Vercel
   WALLET_ENCRYPTION_KEY same as Vercel
   BLOCKCHAIN_RPC_URL    same Alchemy/Infura Sepolia URL as Vercel
   PUBLIC_BASE_URL       https://your-app.vercel.app
   ```
4. Deploy. Render builds `Dockerfile.dashboard` and runs
   `python manage.py run_listener` as the container command — no `CMD` in the
   Dockerfile itself, so this is purely a Render-side override, matching how
   `docker-compose.yml`'s `worker` service already runs it locally.
5. Check the service **Logs** tab for `Gaxtron listener started: {'ETH': True}`.
   If it instead logs `... but some chains are unreachable: ... errors=...`, the
   `errors` value tells you exactly what's wrong (bad RPC key, network block, etc.)
   rather than failing silently.

**Verify it works without any browser tab open:** create a payment, close every
browser tab pointed at the app, send the Sepolia transaction from a wallet, then
watch the Render logs — you should see a `Reconcile tick: {...}` line and the
payment's status flip to `confirmed` in the dashboard purely from the worker's own
5-second poll loop.

(Render's free tier "Background Worker" plan has no always-on guarantee — pick at
least the **Starter** plan for something you'd trust with real payment confirmations.)

## Local dev (no cron)

```powershell
.\scripts\start_eth_product.ps1
# optional manual cron:
curl -H "Authorization: Bearer dev-cron-secret" http://127.0.0.1:8002/api/cron/check-payments
```

Set `CRON_SECRET=dev-cron-secret` in `.env` for local testing.
