param(
    [switch]$Install,
    [switch]$CheckConfig,
    [switch]$Restart,
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

if (!(Test-Path ".env") -and (Test-Path ".env.example")) {
    Copy-Item ".env.example" ".env"
}

if ($CheckConfig) {
    & $VenvPython main.py --check-config
    exit $LASTEXITCODE
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
        Write-Host "Use .\run.ps1 -Restart to stop the existing process and start a fresh server."
        exit 0
    }
}

Write-Host "Starting HiveMindAI at http://$HostName`:$Port/"
& $VenvPython main.py --serve --host $HostName --port $Port
