# Gaxtron ETH Product (Sepolia)

Stripe-style flow for **Ethereum Sepolia only**.

## Customer checkout (hosted page)

**No API for students.** Merchant shares:

`https://your-app.vercel.app/pay/{payment_id}`

The page includes QR code, wallet address, copy buttons, live status, and confirmation — like Stripe Checkout for crypto.

## Architecture

```
Merchant Dashboard
    ----> POST /create-payment
            ----> FastAPI Backend
                    ----> Ethereum Service
                            ----> Generate Address

Customer
    ----> Opens https://PUBLIC_BASE_URL/pay/{payment_id}
            ----> Checkout Page (HTML/JS)
                    ----> Shows address + QR

Customer Wallet
    ----> Sends ETH
            ----> Ethereum Network (Sepolia)

Worker
    ----> Poll blockchain
            ----> Detect transaction
                    ----> Confirm (>= 3 blocks)
                            ----> Update DB
                                    ----> Send Webhook

Dashboard
    ----> GET /verify-payment/{id}
            ----> Shows "confirmed"
```

## Quick start

1. Copy `.env.example` to `.env` and set `BLOCKCHAIN_RPC_URL` (Alchemy/Infura Sepolia).
2. `.\scripts\install_prerequisites.ps1`
3. `.\scripts\start_eth_product.ps1`
4. Register at http://127.0.0.1:8002/register.html
5. Create payment — copy **checkout link**
6. Send Sepolia ETH from faucet to the deposit address
7. Worker confirms after 3 blocks and POSTs webhook

## Public URL

**Recommended:** deploy to Vercel — stable `https://your-app.vercel.app` + Cron. See **VERCEL.md**.

**Local tunnel (dev):**

```powershell
.\scripts\start_eth_product.ps1
.\scripts\start_tunnel.ps1
```

Set `PUBLIC_BASE_URL` to your ngrok/Cloudflare HTTPS URL and restart.

## API

| Endpoint | Auth | Description |
|----------|------|-------------|
| `POST /auth/register` | — | Merchant signup |
| `POST /auth/login` | — | JWT |
| `POST /create-payment` | X-API-Key | `amount`, `callback_url` |
| `GET /payment/{id}` | — | Public status (checkout poll) |
| `GET /pay/{id}` | — | Checkout page |
| `GET /verify-payment/{id}` | X-API-Key | Merchant status |

### Create payment response

```json
{
  "payment_id": 1,
  "payment_url": "https://your-tunnel.ngrok-free.app/pay/1",
  "wallet_address": "0x...",
  "amount": "0.001",
  "status": "pending"
}
```

### Webhook (HMAC in `X-Gaxtron-Signature`)

```json
{
  "status": "confirmed",
  "payment_id": 1,
  "amount": "0.001",
  "tx_hash": "0x..."
}
```

## Testnet ETH

- [Sepolia faucet](https://sepoliafaucet.com/) or Alchemy faucet
- MetaMask network: Sepolia
