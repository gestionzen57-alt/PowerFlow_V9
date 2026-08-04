# install_v9_signal_alerter_task.ps1
# Installe une tache planifiee Windows "V9SignalAlerter" qui tourne
# 24/7 en arriere-plan et envoie des alertes Telegram sur les vraies
# entrees de position detectees par le pipeline V9.
#
# Trigger : AtStartup (auto-boot Windows) + Repetition toutes les 5min
#   (filet de securite si l'AtStartup rate).
# Action  : python -X utf8 scripts/v9_signal_alerter.py
# Le script Python tourne en foreground (boucle infinie) ; la tache
# planifiee le maintient en vie et le relance au boot.
#
# IMPORTANT : Phase 179 R2 additif pur. Zero modif des fichiers
# install_v9_capture_watchdog_task.ps1 ou autres existants. Ce script
# cree une tache distincte "V9SignalAlerter", sans interference avec
# "V9CaptureWatchdog" (principes R28 single-responsibility).
#
# Usage : clic-droit > Executer avec PowerShell (admin)
#         OU : powershell -NoProfile -ExecutionPolicy Bypass -File install_v9_signal_alerter_task.ps1

$ErrorActionPreference = "Stop"

$TASK_NAME = "V9SignalAlerter"
$PYTHON_EXE = "C:\projet\V9\.venv\Scripts\python.exe"
$ALERTER = "C:\projet\V9\scripts\v9_signal_alerter.py"
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
if (-not (Test-Path $ALERTER)) {
    Write-Host "ERREUR : alerter introuvable : $ALERTER" -ForegroundColor Red
    exit 1
}

# Supprime ancienne tache si presente
$existing = Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Tache deja presente — suppression prealable..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
}

# Args pour le script alerter (meme style que v9_capture_watchdog)
$actionArgs = "-X utf8 `"$ALERTER`""

# Action : demarrer python en foreground (le script boucle infinie)
$action = New-ScheduledTaskAction `
    -Execute $PYTHON_EXE `
    -Argument $actionArgs `
    -WorkingDirectory $WORKDIR

# Trigger 1 : AtStartup (auto-boot Windows — true daemon 24/7)
# Trigger 2 : Repetition toutes les 5min (filet de securite)
# Les 2 triggers sont combines via New-ScheduledTaskTriggerSet.
$triggerStartup = New-ScheduledTaskTrigger -AtStartup
$triggerStartup.Delay = "PT30S"  # delai 30s apres boot (le temps que reseau/DB soient prets)

# Repetition : toutes les 5min (300s), duree indefinite
# Note : la repetition sur un AtStartup ne cree pas plusieurs instances ;
# elle assure que si l'AtStartup rate (boot rapide, race), une nouvelle
# tentative demarre 5min plus tard.
$repetition = $triggerStartup.Repetition
$repetition.Interval = "PT5M"  # ISO 8601 duration : 5 minutes
$repetition.StopAtDurationEnd = $false

# Settings : alignes sur v9_capture_watchdog_task.ps1
# RestartCount=0 : si l'alerter meurt, NE SE RELANCE PAS en boucle
# (sinon spam Task Scheduler + creation de N instances paralleles
# qui se tuent entre elles — meme bug documente Phase 168).
# StartWhenAvailable : si le PC etait eteint au moment du trigger,
# la tache s'execute au prochain demarrage.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 0 `
    -ExecutionTimeLimit (New-TimeSpan -Days 365) `
    -MultipleInstances IgnoreNew

# Principal : interactif (utilisateur courant) — necessaire pour
# acceder au loopback 127.0.0.1 sur certaines configs Windows,
# et pour que le process herite de l'env utilisateur (HOME, USERPROFILE).
$principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().User) `
    -LogonType Interactive `
    -RunLevel Highest

# Enregistre la tache
Register-ScheduledTask `
    -TaskName $TASK_NAME `
    -Action $action `
    -Trigger $triggerStartup `
    -Settings $settings `
    -Principal $principal `
    -Description "Alerter Telegram temps reel des entrees de position V9 (Phase 179). Detecte direction directionnelle + confiance>=70 + exploitable, envoie Telegram CEO. Demarrage auto au boot + repetition 5min filet de securite."

Write-Host ""
Write-Host "=== Tache $TASK_NAME installee ===" -ForegroundColor Green
Write-Host ""
Write-Host "Demarrer maintenant :  Start-ScheduledTask -TaskName $TASK_NAME"
Write-Host "Arreter             :  Stop-ScheduledTask -TaskName $TASK_NAME"
Write-Host "Statut              :  Get-ScheduledTask -TaskName $TASK_NAME | Format-List"
Write-Host "Logs en cours       :  Get-EventLog -LogName Application -Source 'TaskScheduler' -Newest 20"
Write-Host "Supprimer           :  Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:`$false"
Write-Host ""
Write-Host "NOTE : trigger AtStartup = daemon 24/7 automatique." -ForegroundColor Cyan
Write-Host "       Aucun lancement manuel requis apres installation." -ForegroundColor Cyan
Write-Host "       Le script lira config\telegram.json (token deja valide)." -ForegroundColor Cyan
Write-Host ""
