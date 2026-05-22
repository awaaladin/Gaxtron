# Gaxtron Multi-Chain Architecture

```
                ┌──────────────────────┐
                │   Frontend (8002)    │
                │   Django (8001)      │
                └─────────┬────────────┘
                          │ REST API
                          ▼
                ┌──────────────────────┐
                │   FastAPI Core       │
                │   PaymentProcessor   │
                └─────────┬────────────┘
                          │
        ┌─────────────────┼─────────────────┬─────────────┐
        ▼                 ▼                 ▼             ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐ ┌──────────────┐
│ EthereumSvc  │  │   TronSvc    │  │ BitcoinSvc   │ │  SolanaSvc   │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘ └──────┬───────┘
       │                 │                 │                │
       ▼                 ▼                 ▼                ▼
  Ethereum RPC      TronGrid API    Blockstream API   Solana RPC
```

## Payment flow

1. `POST /create-payment` with `chain` + `currency` + `amount` + `callback_url`
2. **PaymentProcessor** → chain adapter → generate deposit address (encrypted key in DB)
3. Customer sends crypto on-chain
4. **BlockchainListener** worker polls `check_payment()` per pending row
5. After N confirmations → update DB → HMAC webhook to merchant

## FastAPI + Django

| Layer | Role |
|-------|------|
| **FastAPI** | Auth, payments, API keys, webhooks, worker |
| **Django** | Read-only dashboard (`managed = False` models on same PostgreSQL) |
| **PostgreSQL** | Shared ledger |
| **Redis** | Payment queue + webhook retries + idempotency |

## Supported matrix

| Chain | Currencies |
|-------|------------|
| ETH | ETH, USDT (ERC-20) |
| TRON | TRX, USDT (TRC-20) |
| BTC | BTC |
| SOL | SOL |

## Key modules

- `GaX/app/chains/` — adapter implementations
- `GaX/app/services/payment_processor.py` — central router
- `GaX/app/workers/listener.py` — reconciliation + webhooks
