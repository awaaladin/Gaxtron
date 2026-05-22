# Gaxtron — Crypto Payment Gateway

Production-level blockchain payment gateway (Stripe-style) built with **FastAPI** (core engine) + **Django** (dashboard only) + shared **PostgreSQL** + **Redis** + **web3.py**.

## Architecture

```
Client → FastAPI API (payments, auth, API keys)
              ↓
         PostgreSQL ← Django Dashboard (read-only analytics)
              ↓
         Redis Queue → Blockchain Listener Worker
              ↓
         Webhook POST → Merchant callback_url
```

**Important:** Django never processes payments. All payment logic lives in FastAPI.

## Quick Start (full production loop — Windows)

```powershell
# 1. Start Docker Desktop, then:
.\scripts\install_prerequisites.ps1

# 2. Edit .env — set BLOCKCHAIN_RPC_URL (Sepolia Alchemy/Infura key)

# 3. Start everything (Postgres, Redis, API+UI, worker, Django):
.\scripts\start_full_stack.ps1
```

| Service    | URL |
|-----------|-----|
| Merchant UI + API | http://127.0.0.1:8002/register.html |
| API Docs | http://127.0.0.1:8002/docs |
| Django Dashboard | http://127.0.0.1:8001/ |
| Health | http://127.0.0.1:8002/health |

**Docker (all services):**

```bash
cp .env.example .env
docker compose up -d postgres redis migrate api worker dashboard
```

**Lightweight (API + UI only, SQLite, no worker):** `.\scripts\start_gaxtron.ps1`

## API Endpoints (FastAPI)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/register` | — | Register merchant |
| POST | `/auth/login` | — | Get JWT token |
| POST | `/create-payment` | API Key / JWT | Create payment + wallet |
| GET | `/verify-payment/{id}` | API Key / JWT | Check payment status |
| POST | `/api-keys` | JWT | Generate API key |
| GET | `/health` | — | Health check |

### Create Payment (multi-chain)

```bash
curl -X POST http://127.0.0.1:8002/create-payment \
  -H "X-API-Key: gax_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"amount": "0.01", "chain": "ETH", "currency": "ETH", "callback_url": "https://yoursite.com/webhook"}'
```

Supported chains: `GET /supported-chains` — ETH (ETH/USDT), TRON (TRX/USDT), BTC, SOL.

See `ARCHITECTURE.md` for the adapter-pattern diagram.

## Payment Flow

1. Merchant calls `POST /create-payment` → unique wallet address generated
2. Customer sends crypto to that address
3. **Worker** scans blockchain via web3.py
4. After X confirmations → payment marked `confirmed`
5. **Webhook** POST sent to `callback_url` with HMAC signature

## Database Tables

- `users` — merchants
- `api_keys` — hashed API keys
- `payments` — payment requests (pending/confirmed/failed)
- `transactions` — on-chain tx records
- `wallets` — encrypted private keys (never exposed)
- `webhook_logs` — delivery audit trail

## Django Dashboard

- Merchant stats (payments, revenue)
- Transaction history with filters
- API key viewer (create via FastAPI)
- Webhook delivery logs
- Superadmin panel at `/admin/`

## Project Structure

```
Gaxtron/
├── GaX/app/           # FastAPI core
│   ├── api/routers/   # HTTP endpoints
│   ├── services/      # Business logic
│   ├── db/models/     # SQLAlchemy models
│   └── workers/       # Blockchain listener
├── dashboard/         # Django (display only)
├── docker-compose.yml
└── requirements.txt
```

## Security (Production)

| Control | Implementation |
|---------|----------------|
| API keys | SHA-256 hashed, format-validated, constant-time compare |
| Private keys | Fernet encrypted at rest, never in API responses |
| Payments | API-key-only auth, row-level locking, expiry, idempotency |
| Webhooks | HMAC signatures, SSRF blocking, no redirect follow, retries |
| Auth | bcrypt (12 rounds), login rate limit, JWT with exp/iat |
| Network | CORS allowlist, security headers, HSTS in production |
| Callbacks | HTTPS required in prod, blocks localhost/private IPs |
| Ops | `/health`, `/health/ready`, `/health/live`, fail-closed rate limits |

### Production deploy

```bash
# Generate secrets (32+ chars each)
openssl rand -hex 32

cp .env.example .env
# Set ENV=production DEBUG=False REQUIRE_HTTPS_CALLBACKS=True

docker compose --profile production up -d api-prod worker postgres redis dashboard
alembic -c GaX/alembic.ini upgrade head
```

### Run tests

```bash
cd GaX && pytest tests/ -v
```

## Merchant onboarding flow

Automated end-to-end script (register → API key → payment → verify → dashboard sync):

```bash
# Terminal 1 — start API (local SQLite, no Docker)
cd GaX
set DATABASE_URL=sqlite:///./gaxtron_dev.db   # Windows
uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — run flow
python scripts/merchant_flow.py --sync-dashboard

# Terminal 3 — dashboard (optional)
cd dashboard
set DATABASE_URL=sqlite:///C:/path/to/GaX/gaxtron_dev.db
python manage.py runserver 8001
```

With Docker:

```powershell
.\scripts\start_stack.ps1
python scripts/merchant_flow.py --sync-dashboard
```
