# Generate production .env secrets (run once before deploy)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot | Split-Path -Parent
$out = Join-Path $Root ".env.production.generated"

function New-Secret { param([int]$Bytes = 32); -join ((1..$Bytes) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) }) }

$jwt = New-Secret
$webhook = New-Secret
$wallet = New-Secret
$django = New-Secret 64
$cron = New-Secret

@"

# Generated $(Get-Date -Format o) — copy into .env on your server
ENV=production
DEBUG=False
REQUIRE_HTTPS_CALLBACKS=True

DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/gaxtron_db
REDIS_URL=redis://HOST:6379/0

SECRET_KEY=$jwt
WEBHOOK_SECRET=$webhook
WALLET_ENCRYPTION_KEY=$wallet
DJANGO_SECRET_KEY=$django
CRON_SECRET=$cron

BLOCKCHAIN_RPC_URL=https://eth-mainnet.g.alchemy.com/v2/YOUR_KEY
BLOCKCHAIN_NETWORK=mainnet
ETH_REQUIRED_CONFIRMATIONS=12

ALLOWED_HOSTS=your-domain.com
CSRF_TRUSTED_ORIGINS=https://your-domain.com
PUBLIC_BASE_URL=https://your-domain.com

"@ | Set-Content -Path $out -Encoding UTF8

Write-Host "Wrote $out" -ForegroundColor Green
Write-Host "Edit DATABASE_URL, BLOCKCHAIN_RPC_URL, and domain names before deploying."
