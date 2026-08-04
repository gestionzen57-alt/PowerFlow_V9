# V10 Live Engine — Installation planifiée Windows
# Task Scheduler startup daemon — pas d'ordre réel, signaux only.
# R10 doctrine : zéro capital.

$TaskName = "V10_Live_Engine_Phase7"
$ScriptPath = Join-Path $PSScriptRoot "scripts\v10_live_engine.py"
$PythonExe = "python"   # adapter si venv différent
$WorkingDir = $PSScriptRoot

# Création de la tâche au démarrage (5 min après login)
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$ScriptPath`" --interval 30 --include-a2" `
    -WorkingDirectory $WorkingDir

$Trigger = New-ScheduledTaskTrigger `
    -AtLogOn

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$Principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "V10 Live Paper Daemon - Phase 7. Signalisation only, zero capital (doctrine R10)."

Write-Host "Task '$TaskName' registered. Verify with: Get-ScheduledTask -TaskName $TaskName"
