# Expose local Gaxtron API (port 8002) via ngrok or Cloudflare Tunnel
param(
    [ValidateSet("ngrok", "cloudflare")]
    [string]$Provider = "ngrok",
    [int]$Port = 8002
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_common.ps1"
$Root = Get-GaxtronRoot
Set-GaxtronDevEnv -Root $Root

Write-Host "=== Gaxtron public tunnel (port $Port) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "1. Start the stack first:  .\scripts\start_full_stack.ps1"
Write-Host "2. Run this script in a SECOND terminal"
Write-Host "3. Copy the HTTPS URL into .env as PUBLIC_BASE_URL"
Write-Host "4. Restart API + worker so payment links use the public URL"
Write-Host ""

if ($Provider -eq "ngrok") {
    $ngrok = Get-Command ngrok -ErrorAction SilentlyContinue
    if (-not $ngrok) {
        Write-Host "ngrok not found. Install: https://ngrok.com/download" -ForegroundColor Red
        Write-Host "Then: ngrok config add-authtoken YOUR_TOKEN"
        exit 1
    }
    Write-Host "Starting ngrok http $Port ..." -ForegroundColor Green
    Write-Host "Set in .env:  PUBLIC_BASE_URL=https://YOUR-SUBDOMAIN.ngrok-free.app"
    ngrok http $Port
} else {
    $cf = Get-Command cloudflared -ErrorAction SilentlyContinue
    if (-not $cf) {
        Write-Host "cloudflared not found. Install: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/" -ForegroundColor Red
        exit 1
    }
    Write-Host "Starting Cloudflare quick tunnel to http://127.0.0.1:$Port ..." -ForegroundColor Green
    Write-Host "Set in .env:  PUBLIC_BASE_URL=https://YOUR-TRYCLOUDFLARE-URL"
    cloudflared tunnel --url "http://127.0.0.1:$Port"
}
