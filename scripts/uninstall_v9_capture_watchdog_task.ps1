# uninstall_v9_capture_watchdog_task.ps1
# Supprime la tache planifiee V9CaptureWatchdog.
# Usage : powershell -NoProfile -ExecutionPolicy Bypass -File uninstall_v9_capture_watchdog_task.ps1

$ErrorActionPreference = "Stop"
$TASK_NAME = "V9CaptureWatchdog"

$existing = Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
if (-not $existing) {
    Write-Host "Tache absente — rien a faire."
    exit 0
}

# Stop d'abord si running
$running = Get-ScheduledTask -TaskName $TASK_NAME | Select-Object -ExpandProperty State
if ($running -eq "Running") {
    Write-Host "Tache active — arret..."
    Stop-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
Write-Host "Tache $TASK_NAME supprimee."