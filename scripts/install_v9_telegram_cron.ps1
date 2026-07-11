# install_v9_telegram_cron.ps1 — Installation schtasks 1 daemon Telegram V9.
#
# CEO 2026-07-11 : suite bug boucle "5x mêmes messages".
# Solution : 1 seul daemon via Windows Task Scheduler (auto-restart garanti
# par le système, pas par mon orchestration Background).
#
# Pré-requis : admin PowerShell.
# Usage : powershell -ExecutionPolicy Bypass -File scripts/install_v9_telegram_cron.ps1
#
# Do :
# 1. Tue tous les daemons Telegram existants
# 2. Crée le task V9_TelegramAgent (schtasks, autostart + on-crash)
# 3. Start le task → 1 seul daemon en production
#
# Désinstallation :
#   schtasks /delete /tn V9_TelegramAgent /f

$ErrorActionPreference = 'Stop'
$ProjectRoot = 'C:\projet\V9'
$VenvPython = "$ProjectRoot\.venv\Scripts\python.exe"
$ScriptPath = "$ProjectRoot\scripts\v9_telegram_notifier.py"

Write-Host '═══ Installation V9_TelegramAgent schtasks ═══' -ForegroundColor Cyan

# 1. Tue tous les daemons Telegram existants
Write-Host '[1/3] Tue tous les daemons Telegram en parallèle...'
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
  try {
    $cmd = (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
    if ($cmd -like '*v9_telegram_notifier*') {
      Write-Host "   Killing PID $($_.Id)"
      Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
  } catch {}
}
Start-Sleep -Seconds 2
Write-Host '   ✅ Cleanup terminé' -ForegroundColor Green

# 2. Crée ou met à jour le task
Write-Host '[2/3] Crée/maj task V9_TelegramAgent...'
$existing = schtasks /query /tn V9_TelegramAgent 2>&1
if ($existing -like '*ERROR*') {
  # Création
  schtasks /create /tn V9_TelegramAgent /tr "`"$VenvPython`" `"$ScriptPath`" --watch" /sc onlogon /rl highest /f | Out-Null
  Write-Host '   ✅ Task créé (onlogon)' -ForegroundColor Green
} else {
  # Mise à jour (changement script path)
  schtasks /delete /tn V9_TelegramAgent /f | Out-Null
  schtasks /create /tn V9_TelegramAgent /tr "`"$VenvPython`" `"$ScriptPath`" --watch" /sc onlogon /rl highest /f | Out-Null
  Write-Host '   ✅ Task mis à jour' -ForegroundColor Green
}

# 3. Start le task
Write-Host '[3/3] Démarre V9_TelegramAgent...'
schtasks /run /tn V9_TelegramAgent | Out-Null
Start-Sleep -Seconds 5
$status = schtasks /query /tn V9_TelegramAgent /v /fo list 2>&1 | Select-String 'Status'
Write-Host "   Status : $status"

Write-Host ''
Write-Host '✅ Installation terminée.' -ForegroundColor Green
Write-Host '   Vérifier 1 seul daemon : Get-Process python | Where-Object {$_.CommandLine -like "*v9_telegram*"}'
Write-Host '   Logs        : logs/telegram_notifier.log'
Write-Host '   Conversation: logs/.telegram_conversation.json'
