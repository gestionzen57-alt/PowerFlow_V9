# PowerShell — Installation cron V9_AutoCalibrator (Brief Q2, 2026-07-12)

# À lancer EN ADMINISTRATEUR (clic droit PowerShell > Executer en tant qu'administrateur).
#
# Installe une tache planifiee quotidienne qui invoque
# scripts/v9_auto_calibrator.py --once. Le kill switch
# V9_AUTO_CALIBRATOR_ENABLED reste a 0 (OFF) par defaut : la tache tourne
# mais le script fait un no-op tant que la variable n'est pas mise a 1
# manuellement (jamais fait par ce script — R25', decision manuelle Sondaddy).
#
# Pre-requis :
# - Python venv cree (C:\projet\V9\.venv\Scripts\python.exe doit exister)
# - Compte admin Windows

$ErrorActionPreference = 'Continue'
$V9Root = 'C:\projet\V9'
$Python = 'C:\projet\V9\.venv\Scripts\python.exe'

function Create-V9Task($Name, $Args, $Time) {
    $tr = "`"$Python`" $V9Root\scripts\$Args"
    cmd /c "schtasks /create /tn $Name /tr `"$tr`" /sc daily /st $Time /rl highest /f" *>$null 2>&1
    Start-Sleep -Milliseconds 500
    $check = cmd /c "schtasks /query /tn $Name >nul 2>&1 & echo XXX_$ERRORLEVEL_END & exit /b 0"
    if ($check -match 'XXX_0_END') {
        Write-Host "[OK]   $Name installee (quotidien, $Time)"
        return $true
    }
    Write-Host "[FAIL] $Name"
    return $false
}

$okCount = 0
if (Create-V9Task 'V9_AutoCalibrator' 'v9_auto_calibrator.py --once' '03:00') { $okCount++ }

Write-Host ""
Write-Host "=== $okCount/1 cron V9 auto-calibrateur installe ==="
Write-Host "Kill switch V9_AUTO_CALIBRATOR_ENABLED reste a 0 (OFF) — la tache tourne en no-op"
Write-Host "tant que cette variable n'est pas explicitement mise a 1."

# Verification :
#   Get-ScheduledTask | Where-Object { $_.TaskName -eq 'V9_AutoCalibrator' } | Select-Object TaskName, State
#
# Desinstallation :
#   schtasks /delete /tn "V9_AutoCalibrator" /f
