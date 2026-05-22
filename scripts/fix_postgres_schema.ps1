# Fix outdated Postgres schema (adds chain + confirmations columns)
$ErrorActionPreference = "Stop"
docker exec gaxtron-postgres-1 psql -U gaxtron -d gaxtron_db -v ON_ERROR_STOP=1 -c @"
ALTER TABLE payments ADD COLUMN IF NOT EXISTS chain VARCHAR(10) NOT NULL DEFAULT 'ETH';
ALTER TABLE payments ADD COLUMN IF NOT EXISTS confirmations INTEGER NOT NULL DEFAULT 0;
ALTER TABLE wallets ADD COLUMN IF NOT EXISTS chain VARCHAR(10) NOT NULL DEFAULT 'ETH';
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS chain VARCHAR(10) NOT NULL DEFAULT 'ETH';
CREATE INDEX IF NOT EXISTS ix_payments_chain ON payments (chain);
"@
Write-Host "Schema patched." -ForegroundColor Green
