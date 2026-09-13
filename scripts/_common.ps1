# Shared helpers for Gaxtron scripts (Django backend, port 8001)
$ErrorActionPreference = "Stop"

function Get-GaxtronRoot {
    return $PSScriptRoot | Split-Path -Parent
}

function Set-GaxtronDevEnv {
    param([string]$Root)
    $envPath = Join-Path $Root ".env"
    if (Test-Path $envPath) {
        Get-Content $envPath | ForEach-Object {
            if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
                $name = $matches[1].Trim()
                $val = $matches[2].Trim().Trim('"').Trim("'")
                [Environment]::SetEnvironmentVariable($name, $val, "Process")
            }
        }
    }
    if (-not $env:DATABASE_URL) {
        $dbPath = (Join-Path $Root "gaxtron_dev.db").Replace('\', '/')
        $env:DATABASE_URL = "sqlite:///$dbPath"
    }
    if (-not $env:REDIS_URL) { $env:REDIS_URL = "redis://127.0.0.1:6379/0" }
    if (-not $env:SECRET_KEY) { $env:SECRET_KEY = "dev-jwt-secret-key-minimum-32-characters-long" }
    if (-not $env:WEBHOOK_SECRET) { $env:WEBHOOK_SECRET = "dev-webhook-hmac-secret-minimum-32-chars" }
    if (-not $env:WALLET_ENCRYPTION_KEY) { $env:WALLET_ENCRYPTION_KEY = "dev-wallet-encryption-key-32-chars-min" }
    if (-not $env:DJANGO_SECRET_KEY) { $env:DJANGO_SECRET_KEY = "dev-django-secret-key-minimum-fifty-characters-long" }
    if (-not $env:ENV) { $env:ENV = "development" }
    if (-not $env:DEBUG) { $env:DEBUG = "True" }
    if (-not $env:ALLOWED_HOSTS) { $env:ALLOWED_HOSTS = "localhost,127.0.0.1" }
    if (-not $env:PUBLIC_BASE_URL) { $env:PUBLIC_BASE_URL = "http://127.0.0.1:8001" }
}

function Wait-ForUrl {
    param(
        [string]$Url,
        [int]$MaxSeconds = 90,
        [string]$Label = "service"
    )
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) {
                Write-Host "  $Label ready ($Url)" -ForegroundColor Green
                return $true
            }
        } catch {}
        Start-Sleep -Seconds 2
    }
    Write-Host "  $Label not ready: $Url" -ForegroundColor Yellow
    return $false
}

function Test-DockerAvailable {
    try {
        $out = docker ps --format "{{.Names}}" 2>&1
        return ($LASTEXITCODE -eq 0) -and ($out -notmatch "error|cannot connect")
    } catch { return $false }
}

function Stop-PortListeners {
    param([int[]]$Ports)
    foreach ($port in $Ports) {
        netstat -ano | Select-String ":$port\s" | ForEach-Object {
            if ($_ -match '\s+(\d+)\s*$') {
                Stop-Process -Id $matches[1] -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Start-Sleep -Seconds 1
}
