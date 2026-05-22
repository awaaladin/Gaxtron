# Start Gaxtron stack for local merchant flow
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot | Split-Path -Parent
Set-Location $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example"
}

Write-Host "Starting PostgreSQL and Redis..."
docker compose up -d postgres redis

Write-Host "Waiting for database..."
$max = 30
for ($i = 0; $i -lt $max; $i++) {
    $ok = docker compose exec -T postgres pg_isready -U gaxtron -d gaxtron_db 2>$null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep -Seconds 2
}

Write-Host "Starting API, worker, dashboard..."
docker compose up -d api worker dashboard

Write-Host ""
Write-Host "Stack ready:"
Write-Host "  API:        http://localhost:8000/docs"
Write-Host "  Dashboard:  http://localhost:8001"
Write-Host ""
Write-Host "Run merchant flow:"
Write-Host "  python scripts/merchant_flow.py"
