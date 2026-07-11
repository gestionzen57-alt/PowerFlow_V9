# install_v9_learning_cron.ps1 - Cree le schtasks V9_LearningLoop quotidien.
# P2-C2 audit 2026-07-11 CEO V9 : active la boucle apprentissage learning_loop
# (learning_proposals, cognitive_journal) qui n'etait JAMAIS declenchee.
#
# Usage (admin PowerShell) :
#   powershell -ExecutionPolicy Bypass -File scripts\install_v9_learning_cron.ps1
#
# Frequence : 1 fois / jour a 23h00 UTC (post-cloture marche forex vendredi)
# Commande : v9_ops.py propose 7  (genere propositions sur outcomes 7 derniers jours)
#
# Idempotent : on peut relancer sans probleme (schtasks /create /f ecrase).
# Desinstallation : schtasks /delete /tn V9_LearningLoop /f

$ErrorActionPreference = 'Continue'
$ProjectRoot = 'C:\projet\V9'
$VenvPython = "$ProjectRoot\.venv\Scripts\python.exe"

Write-Host '=== Installation V9_LearningLoop schtasks ===' -ForegroundColor Cyan

# 1. Cree le schtasks (quotidien 23h00 UTC)
$TaskName = 'V9_LearningLoop'
$Trigger = '/sc daily /st 23:00'
$Command = "$VenvPython $ProjectRoot\scripts\v9_ops.py propose 7"

Write-Host "[1/2] Creation schtasks $TaskName..."
$createOut = cmd /c "schtasks /create /tn $TaskName /tr `"$Command`" $Trigger /rl highest /f" 2>&1
Write-Host "   $createOut"

Start-Sleep -Milliseconds 500

# 2. Verification
Write-Host "[2/2] Verification..."
$check = cmd /c "schtasks /query /tn $TaskName >nul 2>&1 & echo XXX_%ERRORLEVEL%_END & exit /b 0"
if ($check -match 'XXX_0_END') {
    Write-Host "[OK]   $TaskName installee - quotidien 23h00 UTC" -ForegroundColor Green
    Write-Host "        Commande : $Command"
    Write-Host "        Premiere execution : aujourd'hui 23:00 UTC"
    Write-Host "        Desinstallation : schtasks /delete /tn $TaskName /f"
    exit 0
} else {
    Write-Host "[FAIL] $TaskName : schtasks /create a echoue (relancer en admin PowerShell)" -ForegroundColor Red
    exit 1
}