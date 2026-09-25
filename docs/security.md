# Security & going live

Gaxtron holds real money on behalf of your users. This page lists what the system guarantees, what
remains your responsibility, and the checklist before switching from the test network to mainnet.

## What the system enforces

- **Double-entry ledger.** Every movement is a balanced set of entries (sum = 0). Balances never go
  negative — checked under row locks and by a database constraint.
- **Append-only history.** Ledger rows cannot be updated or deleted: refused by the application *and* by
  database triggers.
- **Reconciliation.** `python manage.py ledger_reconcile` re-verifies every invariant on live data (balanced
  transactions, balances equal entries, escrow and withdrawal holds equal open items). Run it on a schedule
  and alert on a non-zero exit.
- **Tenant isolation.** Every query is scoped to the calling platform; another platform's ids return `404`.
- **Idempotent money movement.** No retry, race or double-click can pay twice (see
  [idempotency](errors-and-idempotency.md)).
- **Withdrawal controls.** Strict address validation (burn address rejected), manual operator approval by
  default, per-user and per-platform daily caps (a leaked API key cannot drain the platform), and a broadcast
  withdrawal can only be failed after the chain proves it failed — never on a guess.
- **Signed webhooks.** HMAC-SHA256 with a per-platform secret (encrypted at rest) and a timestamp; SSRF-safe
  destination checks; no redirects.
- **Sandbox funding is fail-closed.** `POST /v1/sandbox/credit` exists only when explicitly enabled *and* both
  networks are test networks.

## How the blockchain side is protected

- **Deposits** are credited only from *solidified* (irreversible) transfers of exactly the configured USDT
  contract, so re-orgs, look-alike tokens and dust spam cannot mint balance.
- **Withdrawals never sign what a third party built.** TronGrid assembles the transaction; before signing,
  Gaxtron decodes the exact bytes and requires a single `transfer(recipient, amount)` call on the USDT contract
  from the treasury with no extra fields, a bounded fee limit and a future expiry. Anything else is refused and
  logged as `SECURITY:`. (Checked against real mainnet and Nile transactions.)
- **Crash-safe sending.** The transaction id is stored *before* broadcast. A withdrawal is completed only on
  an irreversible success receipt, and refunded only on an irreversible failure receipt — or when the
  transaction has expired and the network has no record of it. It is never refunded on a guess.
- **Keys.** The treasury key is read from `TRON_TREASURY_PRIVATE_KEY` (environment / secret store) and never
  stored or logged; the sender is disabled if it is unset. Per-user deposit keys are stored Fernet-encrypted.
  The TronGrid API key is only sent to `*.trongrid.io` hosts.
- **Operational note — sweeping.** Deposits arrive at per-user addresses, while withdrawals are paid from the
  treasury. Until automated sweeping exists, an operator must move deposited USDT to the treasury and keep it
  funded with TRX for network fees; monitor that treasury USDT ≥ what users may withdraw.

## Your responsibilities as an integrator

- Keep the API key on your server. Rotate it if it may have leaked; anyone holding it can move your users'
  balances (within the daily limits).
- Verify webhook signatures and reject stale timestamps.
- Authenticate *your own* users before calling Gaxtron on their behalf — Gaxtron trusts your `buyer`/`user`
  fields.
- Show users the destination address before a withdrawal; chain transfers cannot be undone.

## Going live checklist (operators)

1. **Separate everything.** New mainnet deployment, **new database** (never share one with testnet data),
   new API keys and new webhook secrets.
2. **Fresh secrets.** Generate new `SECRET_KEY`, `DJANGO_SECRET_KEY`, `WEBHOOK_SECRET`, `WALLET_ENCRYPTION_KEY`,
   `CRON_SECRET`. Any secret ever pasted into chat, tickets or screenshots is compromised — rotate it.
3. **Network settings.** `TRON_NETWORK=mainnet`, `CONFIRM_MAINNET_DEPLOY=yes-switch-to-mainnet` (set as its
   own deliberate deploy step), a production `TRONGRID_API_KEY`, and leave `ENABLE_SANDBOX_CREDIT` unset.
4. **Treasury key.** Keep the hot-wallet private key in a key-management service or platform secret store —
   never in git, the database, chat or logs. Hold only what withdrawals need; keep the rest in cold storage.
5. **Limits.** Set `WITHDRAWAL_MIN`, `WITHDRAWAL_USER_DAILY_LIMIT`, `WITHDRAWAL_PLATFORM_DAILY_LIMIT` for your
   risk tolerance. Leave `WITHDRAWAL_AUTO_APPROVE_MAX=0` until you have operated manually for a while.
6. **Protect the admin.** Restrict `/admin/` (network allow-list or VPN), use unique strong operator
   passwords, and give database roles no `TRUNCATE`/DDL rights at runtime.
7. **Monitor.** Schedule `ledger_reconcile`; alert on failures, on webhook delivery failures
   (`GET /v1/webhook-events`), and on treasury balance dropping below total customer liabilities.
8. **Dry run with tiny amounts** (a few USDT) end to end — deposit, escrow, release, withdrawal — before
   opening to users.
9. **Legal.** Holding customer funds and offering fiat cash-out is regulated in most jurisdictions. Get
   qualified legal advice before launch.
