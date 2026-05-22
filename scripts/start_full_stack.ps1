# Full Gaxtron stack: Postgres + Redis + FastAPI/UI + Worker + Django
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-GaxtronRoot
$GaX = Join-Path $Root "GaX"
$Dashboard = Join-Path $Root "dashboard"

Set-Location $Root
Set-GaxtronDevEnv -Root $Root

Write-Host "=== Gaxtron - Full production loop (local) ===" -ForegroundColor Cyan

if (-not (Test-DockerAvailable)) {
    Write-Host "Docker required. Run: .\scripts\install_prerequisites.ps1" -ForegroundColor Red
    exit 1
}

$ErrorActionPreference = "Continue"
docker compose up -d postgres redis 2>&1 | Out-Null
$ErrorActionPreference = "Stop"
Start-Sleep -Seconds 6

# Ensure .env uses Docker Postgres on host port 5433
if ($env:DATABASE_URL -match ":5432/") {
    $env:DATABASE_URL = $env:DATABASE_URL -replace ":5432/", ":5433/"
}

Initialize-GaxtronDatabase -GaXDir $GaX

Stop-PortListeners -Ports @(8001, 8002)

Write-Host "Starting FastAPI + merchant UI (port 8002)..."
Start-Process python -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8002" `
    -WorkingDirectory $GaX -WindowStyle Hidden

Write-Host "Starting blockchain worker..."
Start-Process python -ArgumentList "-m","app.workers.runner" `
    -WorkingDirectory $GaX -WindowStyle Hidden

Write-Host "Starting Django dashboard (port 8001)..."
Set-Location $Dashboard
python manage.py migrate --run-syncdb 2>$null | Out-Null
Start-Process python -ArgumentList "manage.py","runserver","127.0.0.1:8001" `
    -WorkingDirectory $Dashboard -WindowStyle Hidden
Set-Location $Root

Start-Sleep -Seconds 4
$apiOk = Wait-ForUrl -Url "http://127.0.0.1:8002/health/live" -MaxSeconds 90 -Label "FastAPI"
$djangoOk = Wait-ForUrl -Url "http://127.0.0.1:8001/" -MaxSeconds 60 -Label "Django"

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8002/health" -TimeoutSec 10
    Write-Host ""
    Write-Host "Health:" -ForegroundColor Cyan
    Write-Host "  status:   $($health.status)"
    Write-Host "  database: $($health.checks.database)"
    Write-Host "  redis:    $($health.checks.redis)"
} catch {
    Write-Host "Could not read /health" -ForegroundColor Yellow
}

Write-Host ""
if ($apiOk -and $djangoOk) {
    Write-Host "Gaxtron full stack is running." -ForegroundColor Green
} else {
    Write-Host "Some services may still be starting - wait 30s and refresh." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Merchant UI:  http://127.0.0.1:8002/register.html"
Write-Host "  API docs:     http://127.0.0.1:8002/docs"
Write-Host "  Django:       http://127.0.0.1:8001/"
Write-Host "  Health:       http://127.0.0.1:8002/health"
Write-Host ""
Write-Host "On-chain flow: set BLOCKCHAIN_RPC_URL in .env (Sepolia), create payment, send test ETH."
Write-Host "Worker polls chain + delivers webhooks via Redis queues."
