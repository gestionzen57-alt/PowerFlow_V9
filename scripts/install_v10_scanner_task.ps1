# install_v10_scanner_task.ps1
# Installe la tache planifiee Windows "V10SignalScanner" qui tourne
# 24/7 en arriere-plan : scanner comportemental SIGNAL-ONLY.
#
# Ce daemon lit les forces_snapshots live, compose les V10 Signals
# (Force + Structure + Contexte via core/v10/) et persiste les setups
# A1/A2 dans docs/V10/v10_signals_latest.json.
#
# PIVOT SIGNAL-ONLY (recommandation audit V10 Phase A) : AUCUN capital
# risque (R10). Ce scanner vend des signaux a Søn pour validation
# manuelle, il ne passe JAMAIS d'ordre.
#
# Trigger : AtStartup (auto-boot Windows) + Repetition toutes les 5min
#   (filet de securite si l'AtStartup rate).
# Action  : pythonw -X utf8 scripts/v10_scanner.py --daemon --timeframe M5
# Le script Python tourne en foreground (boucle 60s) ; la tache le
# maintient en vie et le relance au boot.
#
# Usage : powershell -NoProfile -ExecutionPolicy Bypass -File install_v10_scanner_task.ps1

$ErrorActionPreference = "Stop"

$TASK_NAME = "V10SignalScanner"
# pythonw.exe = windowless (evite une console visible au boot)
$PYTHON_EXE = "C:\projet\V9\.venv\Scripts\pythonw.exe"
$SCANNER = "C:\projet\V9\scripts\v10_scanner.py"
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
if (-not (Test-Path $SCANNER)) {
    Write-Host "ERREUR : scanner introuvable : $SCANNER" -ForegroundColor Red
    exit 1
}

# Supprime ancienne tache si presente
$existing = Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Tache deja presente - suppression prealable..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
}

$actionArgs = "-X utf8 `"$SCANNER`" --daemon --timeframe M5 --top"

$action = New-ScheduledTaskAction `
    -Execute $PYTHON_EXE `
    -Argument $actionArgs `
    -WorkingDirectory $WORKDIR

$triggerStartup = New-ScheduledTaskTrigger -AtStartup
$triggerStartup.Delay = "PT45S"  # delai 45s apres boot (reseau + DB pretes)

$repetition = New-CimInstance -ClassName MSFT_TaskRepetitionPattern `
    -Namespace Root/Microsoft/Windows/TaskScheduler `
    -ClientOnly `
    -Property @{ Interval = "PT5M"; Duration = "P365D"; StopAtDurationEnd = $false }
$triggerStartup.Repetition = $repetition

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 0 `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().User) `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TASK_NAME `
    -Action $action `
    -Trigger $triggerStartup `
    -Settings $settings `
    -Principal $principal `
    -Description "Scanner comportemental V10 SIGNAL-ONLY (pivot edge fund). Lit forces_snapshots live, compose V10 Signals (Force+Structure+Contexte), persiste setups A1/A2 dans docs/V10/v10_signals_latest.json. AUCUN capital risque (R10) : signaux pour validation manuelle Søn, jamais d'ordre."

Write-Host ""
Write-Host "=== Tache $TASK_NAME installee ===" -ForegroundColor Green
Write-Host ""
Write-Host "Demarrer maintenant :  Start-ScheduledTask -TaskName $TASK_NAME"
Write-Host "Arreter             :  Stop-ScheduledTask -TaskName $TASK_NAME"
Write-Host "Supprimer           :  Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:`$false"
Write-Host ""
Write-Host "NOTE : trigger AtStartup = daemon 24/7 automatique." -ForegroundColor Cyan
Write-Host "       PIVOT SIGNAL-ONLY : aucun capital risque, signaux seulement." -ForegroundColor Cyan
Write-Host ""
