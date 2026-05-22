# Gaxtron — API + UI on port 8002 (lightweight; no worker/redis)
# For full loop use: .\scripts\start_full_stack.ps1
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"

$Root = Get-GaxtronRoot
$GaX = Join-Path $Root "GaX"
Set-GaxtronDevEnv -Root $Root

if (-not $env:DATABASE_URL) {
  $env:DATABASE_URL = "sqlite:///$($GaX.Replace('\','/'))/gaxtron_dev.db"
}

Stop-PortListeners -Ports @(8000, 8002)

Write-Host "Starting Gaxtron (API + UI on port 8002)..."
Start-Process python -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8002" `
  -WorkingDirectory $GaX -WindowStyle Hidden

if (Wait-ForUrl -Url "http://127.0.0.1:8002/health/live" -MaxSeconds 90 -Label "Gaxtron") {
  Write-Host ""
  Write-Host "  Open: http://127.0.0.1:8002/register.html" -ForegroundColor Cyan
  Write-Host "  API:  http://127.0.0.1:8002/docs"
  Write-Host ""
  Write-Host "Full production loop: .\scripts\start_full_stack.ps1" -ForegroundColor DarkGray
} else {
  Write-Host "Failed to start. Try: cd GaX; uvicorn app.main:app --host 127.0.0.1 --port 8002" -ForegroundColor Red
  exit 1
}
