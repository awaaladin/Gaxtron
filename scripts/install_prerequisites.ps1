# Install Django dependencies + start PostgreSQL & Redis (Docker, optional)
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-GaxtronRoot
Set-Location $Root

Write-Host "=== Gaxtron - Install prerequisites ===" -ForegroundColor Cyan

# .env from example
$envFile = Join-Path $Root ".env"
$example = Join-Path $Root ".env.example"
if (-not (Test-Path $envFile) -and (Test-Path $example)) {
    Copy-Item $example $envFile
    Write-Host "Created .env from .env.example (edit BLOCKCHAIN_RPC_URL for on-chain tests)"
}

Write-Host "Installing Django packages..."
pip install -q -r (Join-Path $Root "dashboard\requirements.txt")

if (-not (Test-DockerAvailable)) {
    Write-Host ""
    Write-Host "Docker is not running." -ForegroundColor Yellow
    Write-Host "  Full stack (Postgres + Redis + worker) needs Docker."
    Write-Host "  1. Start Docker Desktop"
    Write-Host "  2. Re-run: .\scripts\install_prerequisites.ps1"
    Write-Host ""
    Write-Host "Without Docker you can still run the app on SQLite via .\scripts\start_gaxtron.ps1"
    exit 1
}

Write-Host "Starting PostgreSQL and Redis (Docker)..."
docker compose up -d postgres redis

Write-Host "Waiting for Postgres..."
$pgOk = $false
for ($i = 0; $i -lt 40; $i++) {
    docker compose exec -T postgres pg_isready -U gaxtron -d gaxtron_db 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $pgOk = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $pgOk) { Write-Host "Postgres did not become ready in time" -ForegroundColor Red; exit 1 }
Write-Host "  PostgreSQL ready" -ForegroundColor Green

Write-Host "Waiting for Redis..."
$redisOk = $false
for ($i = 0; $i -lt 30; $i++) {
    docker compose exec -T redis redis-cli ping 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $redisOk = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $redisOk) { Write-Host "Redis did not become ready in time" -ForegroundColor Red; exit 1 }
Write-Host "  Redis ready" -ForegroundColor Green

Write-Host "Applying migrations (fake-initial against existing schema)..."
docker compose run --rm migrate

Write-Host ""
Write-Host "Prerequisites installed. Next:" -ForegroundColor Green
Write-Host "  docker compose up          (full stack: web + worker on Postgres/Redis)"
Write-Host "  .\scripts\start_gaxtron.ps1 (lightweight: Django + SQLite, no Docker)"
