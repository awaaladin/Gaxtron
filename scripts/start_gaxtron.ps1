# Gaxtron — Django backend (site + REST API + hosted checkout), port 8001, SQLite dev DB
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-GaxtronRoot
$Dashboard = Join-Path $Root "dashboard"
Set-GaxtronDevEnv -Root $Root

Stop-PortListeners -Ports @(8001)

Write-Host "Applying migrations..."
Push-Location $Dashboard
try {
    python manage.py migrate --noinput
} finally { Pop-Location }

Write-Host "Starting Gaxtron (Django, port 8001)..."
Start-Process python -ArgumentList "manage.py","runserver","127.0.0.1:8001","--noreload" `
  -WorkingDirectory $Dashboard -WindowStyle Hidden

if (Wait-ForUrl -Url "http://127.0.0.1:8001/health/live" -MaxSeconds 90 -Label "Gaxtron") {
  Write-Host ""
  Write-Host "  Open: http://127.0.0.1:8001/" -ForegroundColor Cyan
  Write-Host ""
  Write-Host "Full stack with Postgres + Redis + worker: docker compose up" -ForegroundColor DarkGray
} else {
  Write-Host "Failed to start. Try: cd dashboard; python manage.py runserver 127.0.0.1:8001" -ForegroundColor Red
  exit 1
}
