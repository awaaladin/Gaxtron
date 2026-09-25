# Mainnet runbook

How to move Gaxtron from the test networks (TRON Nile) to real USDT on TRON mainnet. Do the steps in
order; do not skip the dry run. This is engineering guidance, not legal advice — holding customer funds is
regulated in most countries, so get qualified advice before real users' money is involved.

## 0. Before anything

- [ ] A full end-to-end run on **Nile** has passed: deposit → escrow → release → withdrawal → sweep.
- [ ] You understand the cost model below and have budgeted for it.
- [ ] You have decided who can approve withdrawals and how you will be alerted (see step 8).

### Cost model (TRON)

Every USDT transfer *sent* by Gaxtron (each withdrawal and each sweep) consumes network resources. Without
staked energy they are paid by burning **TRX** from the sending address — typically a few dollars per
transfer at recent prices (check current energy prices). Receiving deposits costs Gaxtron nothing.
Consequences: keep TRX in the treasury; don't sweep tiny balances (`SWEEP_MIN_USDT`); for volume, stake TRX
for energy to cut this sharply.

## 1. Separate everything from testnet

- New **database** (a new Supabase project). Never mix mainnet ledger rows with testnet data.
- New hosting environment/project for the API and for the worker.
- New secrets: `SECRET_KEY`, `DJANGO_SECRET_KEY`, `WEBHOOK_SECRET`, `WALLET_ENCRYPTION_KEY`, `CRON_SECRET`.
  Anything ever pasted into chat, screenshots or tickets is compromised — do not reuse it.
- New API keys for every platform that integrates.

## 2. Create the treasury wallet

- Generate a **brand-new** TRON key in a wallet you trust. Never reuse a key from tests or examples, and never
  use a key that looks patterned (`1111…`): such keys are swept by bots within seconds.
- Fund it with **TRX** (fees) and a small **USDT float** for withdrawals. Keep the rest of your money elsewhere —
  the treasury is a hot wallet.
- Put the private key **only** in the *worker's* secret store, never in git, the database, chat or logs. The web
  API does not need it.

## 3. Environment variables

| Variable | Web API | Worker | Notes |
|---|---|---|---|
| `TRON_NETWORK=mainnet` | ✅ | ✅ | |
| `CONFIRM_MAINNET_DEPLOY=yes-switch-to-mainnet` | ✅ | ✅ | Set as its own deliberate deploy step |
| `TRONGRID_API_KEY` | ✅ | ✅ | Production key (mainnet USDT contract is built in) |
| `DATABASE_URL`, `REDIS_URL`, all secrets from step 1 | ✅ | ✅ | |
| `TRON_TREASURY_PRIVATE_KEY` | ❌ | ✅ | Worker only. Unset = sending and sweeping are disabled (the kill switch) |
| `TRON_TREASURY_ADDRESS` | ❌ | ✅ | Expected address; startup fails if it does not match the key |
| `WITHDRAWAL_MIN`, `WITHDRAWAL_USER_DAILY_LIMIT`, `WITHDRAWAL_PLATFORM_DAILY_LIMIT` | ✅ | ✅ | Start very low (e.g. 5 / 50 / 200) |
| `WITHDRAWAL_AUTO_APPROVE_MAX=0` | ✅ | ✅ | Manual approval of every withdrawal until you trust the system |
| `SWEEP_MIN_USDT`, `SWEEP_TRX_TARGET_SUN`, `SWEEP_FEE_LIMIT_SUN` | | ✅ | Defaults: 20 USDT / 40 TRX / 40 TRX |
| `ENABLE_SANDBOX_CREDIT` | leave **unset** | leave **unset** | Disabled automatically on mainnet as well |

The old Ethereum gateway settings (`BLOCKCHAIN_*`, Alchemy) are unrelated to the USDT ledger; leave them on
their test network.

## 4. Deploy and migrate

Deploy the API and the worker (the worker runs `python manage.py run_listener`, which also drives the TRON
deposit watcher, sender and sweeper). Run `python manage.py migrate` against the new database, create the
platform account and its API key, and set its webhook URL.

## 5. Dry run with tiny amounts

With real USDT you can afford to lose (a few dollars):
1. `POST /v1/users/{id}/deposit-address`, send a small USDT (TRC-20) amount, confirm the balance is credited.
2. Escrow it between two test users, release it, check both balances.
3. Request a withdrawal, approve it in `/admin/`, confirm it arrives and shows `completed`.
4. Let a sweep run (or temporarily lower `SWEEP_MIN_USDT`) and confirm the deposit lands in the treasury.
5. Run `python manage.py ledger_reconcile` — it must print "Ledger is consistent."

## 6. Open gradually

Keep the low limits at first and raise them only as you gain confidence. Approve withdrawals by hand.

## 7. Restrict the admin

`/admin/` can approve withdrawals. Put it behind an IP allow-list or VPN, use unique strong passwords for
each operator, and give the runtime database role no `TRUNCATE` or DDL rights.

## 8. Monitor

- Run `ledger_reconcile` on a schedule and alert on a non-zero exit.
- Alert on failed webhook deliveries (`GET /v1/webhook-events`) and on `SECURITY:` log lines.
- Watch the treasury: **USDT ≥ what users may withdraw**, and **TRX for fees**.
- Watch deposit addresses that hold credited USDT below the sweep minimum — that is custody, too.

## Emergency stop

Remove `TRON_TREASURY_PRIVATE_KEY` from the worker: nothing can be sent or swept, while deposits keep being
credited. To stop new withdrawals as well, set `WITHDRAWAL_MIN` very high or revoke the platform's API key.

## Later hardening

- Encrypt deposit keys with a *public* key so the web tier can create addresses but only the worker (or a KMS)
  can decrypt them.
- Stake TRX for energy, and consider multi-signature or a cold-storage sweep for large balances.
