# install_v9_capture_watchdog_task.ps1
# Installe une tache planifiee Windows "V9CaptureWatchdog" qui supervise
# le port 31685 et relance core.v9.capture_server si KO.
#
# Trigger : MANUEL (l'utilisateur lance apres MT4).
# Action  : python -X utf8 scripts/v9_capture_watchdog.py
# Le script Python tourne en foreground ; la tache le maintient en vie.
#
# Usage : clic-droit > Executer avec PowerShell (admin)
#         OU : powershell -NoProfile -ExecutionPolicy Bypass -File install_v9_capture_watchdog_task.ps1

$ErrorActionPreference = "Stop"

$TASK_NAME = "V9CaptureWatchdog"
$PYTHON_EXE = "C:\projet\V9\.venv\Scripts\python.exe"
$WATCHDOG = "C:\projet\V9\scripts\v9_capture_watchdog.py"
$WORKDIR = "C:\projet\V9"

# Verif admin
if (-not (New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent()
)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERREUR : privileges administrateur requis." -ForegroundColor Red
    exit 1
}

# Verif fichiers
if (-not (Test-Path $PYTHON_EXE)) {
    Write-Host "ERREUR : python introuvable : $PYTHON_EXE" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $WATCHDOG)) {
    Write-Host "ERREUR : watchdog introuvable : $WATCHDOG" -ForegroundColor Red
    exit 1
}

# Supprime ancienne tache si presente
$existing = Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Tache deja presente — suppression prealable..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
}

# Args pour le script watchdog
$actionArgs = "-X utf8 `"$WATCHDOG`""

# Action : demarrer python en foreground (le watchdog boucle infinie)
$action = New-ScheduledTaskAction `
    -Execute $PYTHON_EXE `
    -Argument $actionArgs `
    -WorkingDirectory $WORKDIR

# Trigger : aucun (manuel). StartWhenAvailable=False ; demarrage via
# Start-ScheduledTask depuis le menu contextuel ou script dedie.
$trigger = New-ScheduledTaskTrigger -AtLogOn  # fallback pratique : au login
# On override : pas de trigger automatique. La tache est en "manual".
$trigger = $null

# Settings : pas de redemarrage auto (Phase 168, 03/08/2026).
# Auparavant RestartCount=3 → boucle doublon-kill-restart : le watchdog
# qui crashait etait relance jusqu'a 3 fois par TaskScheduler, creant
# 2-4 instances paralleles qui se tuaient entre elles.
# RestartCount=0 : si le watchdog meurt, il NE SE RELANCE PAS.
# L'admin doit investiguer manuellement avant de redemarrer.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 0 `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -MultipleInstances IgnoreNew

# Principal : interactif (utilisateur courant) — necessaire pour acceder
# au loopback 127.0.0.1 sur certaines configs Windows.
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().User) `
    -LogonType Interactive `
    -RunLevel Highest

# Enregistre la tache (sans trigger = manuelle)
Register-ScheduledTask `
    -TaskName $TASK_NAME `
    -Action $action `
    -Settings $settings `
    -Principal $principal `
    -Description "Surveille port 31685 et relance core.v9.capture_server si KO. Lancement manuel apres MT4."

Write-Host ""
Write-Host "=== Tache $TASK_NAME installee ===" -ForegroundColor Green
Write-Host ""
Write-Host "Demarrer :  Start-ScheduledTask -TaskName $TASK_NAME"
Write-Host "             OU  scripts\start_v9_capture_watchdog.bat"
Write-Host "Arreter :  Stop-ScheduledTask -TaskName $TASK_NAME"
Write-Host "             OU  scripts\stop_v9_capture_watchdog.bat"
Write-Host "Supprimer : scripts\uninstall_v9_capture_watchdog_task.ps1"
Write-Host ""
Write-Host "NOTE : tache en mode MANUEL. Lancer APRES MT4." -ForegroundColor Yellow
Write-Host ""