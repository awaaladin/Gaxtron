# Gaxtron MVP — Market launch checklist

## Run locally (full stack)

```powershell
.\scripts\install_prerequisites.ps1   # once: Docker Postgres + Redis + pip
.\scripts\start_full_stack.ps1      # API + worker + Django
```

Then open: **http://127.0.0.1:8002/register.html**

Lightweight (no Redis/worker): `.\scripts\start_gaxtron.ps1`

## Security (built-in)

| Control | Status |
|---------|--------|
| bcrypt passwords (12 rounds) | Yes |
| JWT + API key auth | Yes |
| SHA-256 hashed API keys | Yes |
| Fernet-encrypted wallet keys | Yes |
| Webhook HMAC signatures | Yes |
| SSRF protection on callbacks | Yes |
| Rate limiting (Redis) | Yes |
| Double-spend / idempotency | Yes |
| Security headers (HSTS, CSP, nosniff) | Yes (production) |
| Row-level payment locking | Yes |

## Production deploy

1. Generate secrets: `openssl rand -hex 32` (×3)
2. Set `ENV=production`, `DEBUG=False`, `REQUIRE_HTTPS_CALLBACKS=True`
3. Use PostgreSQL + Redis (Docker Compose)
4. Set `BLOCKCHAIN_RPC_URL` to a paid provider (Alchemy/Infura)
5. Run worker: `python -m app.workers.runner`
6. Put HTTPS reverse proxy (nginx/Caddy) in front of API
7. Serve UI from same domain as API (`/app/`) to avoid CORS

```bash
docker compose --profile production up -d
```

## Transaction flow

1. Merchant registers → API key issued
2. `POST /create-payment` → unique deposit address
3. Customer sends ETH/USDT on-chain
4. Worker confirms after N blocks → updates payment
5. Signed webhook POST to merchant `callback_url`

## Before going live with real money

- [ ] Test on Sepolia/testnet with small amounts
- [ ] Verify webhooks reach your server
- [ ] Rotate all default secrets
- [ ] Legal: Terms of Service + Privacy Policy
- [ ] Monitoring: `/health/ready` uptime checks
