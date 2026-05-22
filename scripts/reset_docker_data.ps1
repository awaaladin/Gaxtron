# Reset Postgres + Redis volumes (fixes password / stale data issues)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot | Split-Path -Parent
Set-Location $Root
Write-Host "Stopping stack and removing volumes..."
docker compose down -v
Write-Host "Done. Run .\scripts\install_prerequisites.ps1 then .\scripts\start_full_stack.ps1"
