# ChainPay frontend on port 8002
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot | Split-Path -Parent
$Frontend = Join-Path $Root "frontend"
Set-Location $Frontend

Write-Host "ChainPay UI: http://127.0.0.1:8002"
Write-Host "API backend: http://127.0.0.1:8000 (start FastAPI separately)"
Write-Host ""
python -m http.server 8002 --bind 127.0.0.1
