# install_v9_crons.ps1 - Cree ou met a jour les 3 taches planifiees V9
# (equivalent PowerShell de install_heartbeat_cron.bat, a utiliser quand
# le BAT bloque sous MSYS).
#
# Usage : powershell -ExecutionPolicy Bypass -File scripts/install_v9_crons.ps1
#
# Chantier 2026-07-09 supervision H24 - voir DECISIONS_LOG chantier DB vivante 24/7.
# Script en ASCII pur pour compatibilite PowerShell 5 cp1252 (Windows 10).
#
# Approche : on n'essaie PAS de tester l'existence prealablement (les messages
# d'erreur schtasks dans PS5 cassent l'enchainement). On cree simplement,
# on verifie APRES si la tache est la, si oui on log [CREEE], sinon [ERREUR].
# Idempotent : on peut relancer sans probleme si les 3 existent deja
# (schtasks /create ecrase l'existante avec /f).

$ErrorActionPreference = "Continue"
$V9Root = if ($env:V9_ROOT) { $env:V9_ROOT } else { "C:\projet\V9" }

function Create-V9Task {
    param(
        [string]$Name,
        [string]$Script,
        [string]$Arg,
        [int]$Minutes
    )
    $tr = "python $V9Root\scripts\$Script $Arg"
    cmd /c "schtasks /create /tn $Name /tr `"$tr`" /sc minute /mo $Minutes /rl highest /f" *>$null 2>&1
    Start-Sleep -Milliseconds 500
    # Verification post-creation : on utilise schtasks query avec redirection
    # via cmd /c + echo de ERRORLEVEL de la commande AVANT un echo final.
    $check = cmd /c "schtasks /query /tn $Name >nul 2>&1 & echo XXX_%ERRORLEVEL%_END & exit /b 0"
    # ps ne capture que stdout
    if ($check -match "XXX_0_END") {
        Write-Host "[OK]   $Name installee - toutes les $Minutes min"
        return $true
    }
    Write-Host "[FAIL] $Name : schtasks /query a retourne un code != 0"
    return $false
}

Write-Host ""
Write-Host "=== Installation 3 crons V9 (V9Root = $V9Root) ==="
Write-Host ""

$okCount = 0
if (Create-V9Task -Name "V9_HeartbeatCheck" -Script "v9_heartbeat.py"  -Arg "--check"        -Minutes 5)  { $okCount++ }
if (Create-V9Task -Name "V9_HeartbeatAlert" -Script "v9_heartbeat.py"  -Arg "--heartbeat"   -Minutes 60) { $okCount++ }
if (Create-V9Task -Name "V9_AutoRestart"    -Script "v9_supervisor.py" -Arg "--autorestart" -Minutes 5)  { $okCount++ }

Write-Host ""
if ($okCount -eq 3) {
    Write-Host "[DONE] 3/3 taches planifiees V9 actives."
    Write-Host "Verification : schtasks /query /tn V9_*"
    exit 0
} else {
    Write-Host "[FAIL] $okCount/3 taches installees."
    exit 1
}
