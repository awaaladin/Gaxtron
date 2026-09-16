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

**Scaling note:** `run_listener` used to re-scan the full `BLOCKCHAIN_SCAN_BLOCKS` window
on every 5s tick for every pending payment that hadn't found its tx yet — fine for one
payment, O(pending × 500 RPC calls) at real volume. It now tracks `last_scanned_block`
per payment and only scans forward from there (a fresh payment starts at its creation
block, no lookback at all), so cost no longer grows with how many payments are waiting.
Once a tx is found, confirmation checks were always cheap (2 RPC calls) and still are.

## 7. Alchemy Address Activity webhook (optional — instant detection)

Even with the scan fix above, detection is still poll-based: a deposit isn't *noticed*
until the next 5s tick. Alchemy's Address Activity webhook pushes a notification the
moment a matching tx is mined, so this app can react immediately instead of waiting for
the next poll. It's optional and inert until configured — without it, `run_listener`'s
poll loop (now cheap, see above) is the only detection path, same as before.

1. **Create the webhook**: Alchemy dashboard → **Notify** → **Create Webhook** →
   **Address Activity** → network **Sepolia** → webhook URL
   `https://your-app.vercel.app/webhooks/alchemy/address-activity` → no addresses need
   adding upfront, the app registers each deposit address itself as payments are created.
2. Copy that webhook's **Signing Key** and **Webhook ID** from its settings page.
3. Get an **Auth Token** (not the signing key) from Alchemy dashboard → account/team
   settings → **Auth Tokens** — this is what lets the app call Alchemy's API to add each
   new deposit address to the webhook's watch list.
4. Set on **both** Vercel and Render (same values on each, like the other shared secrets):
   ```
   ALCHEMY_WEBHOOK_SIGNING_KEY   from step 2
   ALCHEMY_WEBHOOK_ID            from step 2
   ALCHEMY_AUTH_TOKEN            from step 3
   ```
5. Redeploy both. Create a test payment and check the Render worker logs — you should
   see the payment flip to `confirmed` within a couple seconds of the tx confirming,
   instead of on the next 5s tick.

If any of the three env vars is missing, `alchemy_webhook_service.is_configured()`
returns `False` and nothing about payment creation or detection changes — the endpoint
itself just 401s anything sent to it, since signature verification has no key to check
against.

## Local dev (no cron)

```powershell
.\scripts\start_eth_product.ps1
# optional manual cron:
curl -H "Authorization: Bearer dev-cron-secret" http://127.0.0.1:8002/api/cron/check-payments
```

Set `CRON_SECRET=dev-cron-secret` in `.env` for local testing.
