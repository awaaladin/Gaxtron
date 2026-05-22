# ETH-only Sepolia product: Postgres + Redis + API:8002 + Worker
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-GaxtronRoot
$GaX = Join-Path $Root "GaX"
Set-Location $Root
Set-GaxtronDevEnv -Root $Root

if (-not $env:ENABLED_CHAINS) { $env:ENABLED_CHAINS = "ETH" }
if (-not $env:PUBLIC_BASE_URL) { $env:PUBLIC_BASE_URL = "http://127.0.0.1:8002" }
if (-not $env:BLOCKCHAIN_NETWORK) { $env:BLOCKCHAIN_NETWORK = "sepolia" }

Write-Host "=== Gaxtron ETH Product (Sepolia) ===" -ForegroundColor Cyan
Write-Host "PUBLIC_BASE_URL = $env:PUBLIC_BASE_URL"
Write-Host ""

if (Test-DockerAvailable) {
    docker compose up -d postgres redis 2>&1 | Out-Null
    Start-Sleep -Seconds 5
    if ($env:DATABASE_URL -match ":5432/") {
        $env:DATABASE_URL = $env:DATABASE_URL -replace ":5432/", ":5433/"
    }
} else {
    Write-Host "Docker not running - using DATABASE_URL from .env" -ForegroundColor Yellow
}

try {
    Initialize-GaxtronDatabase -GaXDir $GaX
} catch {
    Write-Host "Database init failed. Start Docker Desktop, then: docker compose up -d postgres redis" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
Stop-PortListeners -Ports @(8002)

Write-Host "Starting FastAPI + checkout UI on :8002 ..."
Start-Process python -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8002" `
    -WorkingDirectory $GaX -WindowStyle Hidden

Write-Host "Starting Sepolia payment worker ..."
Start-Process python -ArgumentList "-m","app.workers.runner" `
    -WorkingDirectory $GaX -WindowStyle Hidden

Start-Sleep -Seconds 4
$ok = Wait-ForUrl -Url "http://127.0.0.1:8002/health/live" -MaxSeconds 90 -Label "API"

Write-Host ""
if ($ok) {
    Write-Host "ETH product is running." -ForegroundColor Green
} else {
    Write-Host "API still starting - wait and open health URL." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Register:     http://127.0.0.1:8002/register.html"
Write-Host "  Dashboard:    http://127.0.0.1:8002/dashboard.html"
Write-Host "  API docs:     http://127.0.0.1:8002/docs"
Write-Host ""
Write-Host "Public checkout (set PUBLIC_BASE_URL for real wallets):"
Write-Host "  Example link: $($env:PUBLIC_BASE_URL)/pay/1"
Write-Host ""
Write-Host "Tunnel (second terminal):  .\scripts\start_tunnel.ps1"
Write-Host "After tunnel: set PUBLIC_BASE_URL in .env, restart this script."
