# Run FastAPI (8000) and Django dashboard (8001) together
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot | Split-Path -Parent
$DbPath = Join-Path $Root "GaX\gaxtron_dev.db"
$DbUrl = "sqlite:///$($DbPath.Replace('\','/'))"

$env:DATABASE_URL = $DbUrl
$env:SECRET_KEY = "dev-jwt-secret-key-minimum-32-characters-long"
$env:WEBHOOK_SECRET = "dev-webhook-hmac-secret-minimum-32-chars"
$env:WALLET_ENCRYPTION_KEY = "dev-wallet-encryption-key-32-chars-min"
$env:ENV = "development"
$env:DEBUG = "True"
$env:FASTAPI_URL = "http://127.0.0.1:8000"
$env:DJANGO_SECRET_KEY = "dev-django-secret-key-minimum-fifty-characters-long"

Write-Host "Shared DB: $DbUrl"
Write-Host ""

# FastAPI
$apiRunning = $false
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health/live" -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) { $apiRunning = $true }
} catch {}

if (-not $apiRunning) {
    Write-Host "Starting FastAPI on http://127.0.0.1:8000 ..."
    Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000" -WorkingDirectory (Join-Path $Root "GaX") -WindowStyle Minimized
    Start-Sleep -Seconds 6
} else {
    Write-Host "FastAPI already running on http://127.0.0.1:8000"
}

# Django migrate + runserver
Write-Host "Starting Django on http://127.0.0.1:8001 ..."
$dashboard = Join-Path $Root "dashboard"
Set-Location $dashboard
python manage.py migrate --run-syncdb 2>$null | Out-Null
Start-Process -FilePath "python" -ArgumentList "manage.py","runserver","127.0.0.1:8001" -WorkingDirectory $dashboard -WindowStyle Minimized
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "Starting ChainPay frontend on http://127.0.0.1:8002 ..."
Start-Process -FilePath "python" -ArgumentList "-m","http.server","8002","--bind","127.0.0.1" -WorkingDirectory (Join-Path $Root "frontend") -WindowStyle Minimized

Write-Host ""
Write-Host "Services:"
Write-Host "  ChainPay UI:      http://127.0.0.1:8002/"
Write-Host "  FastAPI API:      http://127.0.0.1:8000/docs"
Write-Host "  Django Dashboard: http://127.0.0.1:8001/"
Write-Host ""
Write-Host "Login: merchant_flow_test@gaxtron.dev / SecureMerchantP@ss1"
