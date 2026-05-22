# Run merchant flow locally without Docker (SQLite dev mode)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot | Split-Path -Parent
Set-Location $Root

$env:DATABASE_URL = "sqlite:///./gaxtron_dev.db"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:ENV = "development"
$env:DEBUG = "True"
if (-not $env:SECRET_KEY) {
    $env:SECRET_KEY = "dev-jwt-secret-key-minimum-32-characters-long"
    $env:WEBHOOK_SECRET = "dev-webhook-hmac-secret-minimum-32-chars"
    $env:WALLET_ENCRYPTION_KEY = "dev-wallet-encryption-key-32-chars-min"
}

Write-Host "Starting FastAPI on http://localhost:8000 ..."
$apiJob = Start-Job -ScriptBlock {
    Set-Location $using:Root
    $env:DATABASE_URL = $using:env:DATABASE_URL
    $env:SECRET_KEY = $using:env:SECRET_KEY
    $env:WEBHOOK_SECRET = $using:env:WEBHOOK_SECRET
    $env:WALLET_ENCRYPTION_KEY = $using:env:WALLET_ENCRYPTION_KEY
    $env:ENV = "development"
    $env:DEBUG = "True"
    Set-Location "$using:Root\GaX"
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 2>&1
}

Start-Sleep -Seconds 8

Write-Host "Running merchant flow..."
Set-Location $Root
python scripts/merchant_flow.py --sync-dashboard

Write-Host "`nStopping API..."
Stop-Job $apiJob -ErrorAction SilentlyContinue
Remove-Job $apiJob -Force -ErrorAction SilentlyContinue
