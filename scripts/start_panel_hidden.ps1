$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonCmd = "py"
$streamlitArgs = "-m streamlit run app.py --server.headless true --server.port 8501 --server.address 127.0.0.1"

$alreadyRunning = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
if (-not $alreadyRunning) {
    Start-Process -FilePath $pythonCmd -ArgumentList $streamlitArgs -WorkingDirectory $projectRoot -WindowStyle Hidden
    Start-Sleep -Seconds 3
}

Start-Process "http://127.0.0.1:8501"
Write-Host "Panel disponible en http://127.0.0.1:8501"
