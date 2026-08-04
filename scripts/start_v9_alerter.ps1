# start_v9_alerter.ps1 — Phase 179 (03/08) : lanceur Windows v9_signal_alerter
#
# R2 additif pur : nouveau fichier scripts/. Aucun impact sur le pipeline.
# R6 fail-open : si Telegram non configuré, le script log en console uniquement.
#
# Usage :
#   powershell -NoProfile -File scripts\start_v9_alerter.ps1
#
# Variables d'env (optionnelles, sinon lues depuis config\telegram.json) :
#   $env:V9_TELEGRAM_BOT_TOKEN = "..."   # bot Telegram
#   $env:V9_TELEGRAM_CHAT_ID   = "..."   # chat ID CEO

$ErrorActionPreference = "Continue"

# Charger telegram.json si pas en env
if (-not $env:V9_TELEGRAM_BOT_TOKEN -or -not $env:V9_TELEGRAM_CHAT_ID) {
    $tgConfigPath = Join-Path $PSScriptRoot "..\config\telegram.json"
    if (Test-Path $tgConfigPath) {
        try {
            $tgConfig = Get-Content $tgConfigPath -Raw | ConvertFrom-Json
            if (-not $env:V9_TELEGRAM_BOT_TOKEN) {
                $env:V9_TELEGRAM_BOT_TOKEN = $tgConfig.BOT_TOKEN
            }
            if (-not $env:V9_TELEGRAM_CHAT_ID) {
                $env:V9_TELEGRAM_CHAT_ID = $tgConfig.CHAT_ID
            }
        } catch {
            Write-Host "[start_v9_alerter] WARN: telegram.json illisible: $_" -ForegroundColor Yellow
        }
    } else {
        Write-Host "[start_v9_alerter] INFO: pas de config\telegram.json → mode console (R6 fail-open)" -ForegroundColor Yellow
    }
}

$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$script = Join-Path $PSScriptRoot "v9_signal_alerter.py"

if (-not (Test-Path $venvPython)) {
    Write-Host "[start_v9_alerter] ERREUR: venv introuvable: $venvPython" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $script)) {
    Write-Host "[start_v9_alerter] ERREUR: script introuvable: $script" -ForegroundColor Red
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " V9 Signal Alerter (Phase 179)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Python : $venvPython"
Write-Host "Script : $script"
Write-Host "Token  : $(if ($env:V9_TELEGRAM_BOT_TOKEN) { '***' + $env:V9_TELEGRAM_BOT_TOKEN.Substring([Math]::Max(0, $env:V9_TELEGRAM_BOT_TOKEN.Length - 8)) } else { '(absent, mode console)' })"
Write-Host "Chat   : $(if ($env:V9_TELEGRAM_CHAT_ID) { $env:V9_TELEGRAM_CHAT_ID } else { '(absent, mode console)' })"
Write-Host "============================================================" -ForegroundColor Cyan

& $venvPython $script
