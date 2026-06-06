param(
    [switch]$Install,
    [switch]$CheckConfig,
    [switch]$Restart,
    [string]$OpenRouterApiKey = "",
    [string]$MongoDbUri = "",
    [string]$RedisUrl = "",
    [string]$Model = "qwen/qwen3-coder:free",
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path $VenvPython)) {
    python -m venv .venv
}

if ($Install) {
    & $VenvPython -m pip install -r requirements.txt
}

if (!(Test-Path ".env") -and (Test-Path ".env.local.example")) {
    Copy-Item ".env.local.example" ".env"
}

$env:APP_STACK = "free"
$env:LLM_PROVIDER = "openrouter"
$env:OPENROUTER_MODEL = $Model
$env:OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
$env:OPENROUTER_SITE_URL = "http://$HostName`:$Port"
$env:OPENROUTER_APP_NAME = "HiveMindAI"
$env:LLM_REQUEST_TIMEOUT_SECONDS = "20"
$env:MONGODB_DATABASE = "hivemindai"
$env:SWARM_STRICT_INTEGRATIONS = "false"
$env:SWARM_ENABLE_LOCAL_FALLBACKS = "true"
$env:APP_HOST = $HostName
$env:APP_PORT = "$Port"
$env:APP_BASE_URL = "http://$HostName`:$Port"

if ($OpenRouterApiKey) {
    $env:OPENROUTER_API_KEY = $OpenRouterApiKey
}
if ($MongoDbUri) {
    $env:MONGODB_URI = $MongoDbUri
}
if ($RedisUrl) {
    $env:REDIS_URL = $RedisUrl
}

if ($CheckConfig) {
    & $VenvPython main.py --check-local-config
    exit $LASTEXITCODE
}

if (!$env:OPENROUTER_API_KEY) {
    Write-Host "OPENROUTER_API_KEY is not set. The app will still run with deterministic local fallbacks."
    Write-Host "To use the free OpenRouter model: .\run-local-free.ps1 -OpenRouterApiKey YOUR_KEY"
}

$Existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Existing) {
    if ($Restart) {
        $Existing | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object {
            Stop-Process -Id $_ -Force
        }
        Start-Sleep -Seconds 1
    } else {
        Write-Host "HiveMindAI already appears to be running at http://$HostName`:$Port/"
        Write-Host "Use .\run-local-free.ps1 -Restart to stop the existing process and start a fresh server."
        exit 0
    }
}

Write-Host "Starting HiveMindAI local/free mode at http://$HostName`:$Port/"
Write-Host "LLM provider: OpenRouter; model: $Model"
& $VenvPython main.py --serve --host $HostName --port $Port
