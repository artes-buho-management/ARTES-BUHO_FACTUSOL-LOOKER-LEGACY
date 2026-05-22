$ErrorActionPreference = "Stop"

$pids = @()
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | ForEach-Object {
    if ($_.CommandLine -and $_.CommandLine -match "streamlit run app.py") {
        $pids += $_.ProcessId
    }
}

if ($pids.Count -eq 0) {
    Write-Host "No hay proceso del panel activo."
    exit 0
}

$pids | ForEach-Object {
    Stop-Process -Id $_ -Force
}

Write-Host "Panel detenido. Procesos cerrados: $($pids -join ', ')"
