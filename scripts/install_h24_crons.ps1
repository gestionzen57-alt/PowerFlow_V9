# PowerShell — Installation 4 crons H24 AUTOPILOT

> À lancer EN ADMINISTRATEUR (clic droit PowerShell > Executer en tant qu'administrateur).

## Pré-requis

- Python venv créé (`C:\projet\V9\.venv\Scripts\python.exe` doit exister)
- 3 crons V9 déjà installés (V9_HeartbeatCheck / V9_HeartbeatAlert / V9_AutoRestart)
- Compte admin Windows

## Commandes

```powershell
# Ouvrir PowerShell en admin
# Puis :
Set-Location C:\projet\V9

$ErrorActionPreference = 'Continue'
$V9Root = 'C:\projet\V9'
$Python = 'C:\projet\V9\.venv\Scripts\python.exe'

function Create-V9Task($Name, $Args, $Minutes) {
    $tr = "`"$Python`" $V9Root\scripts\$Args"
    cmd /c "schtasks /create /tn $Name /tr `"$tr`" /sc minute /mo $Minutes /rl highest /f" *>$null 2>&1
    Start-Sleep -Milliseconds 500
    $check = cmd /c "schtasks /query /tn $Name >nul 2>&1 & echo XXX_$ERRORLEVEL_END & exit /b 0"
    if ($check -match 'XXX_0_END') {
        Write-Host "[OK]   $Name installee (toutes les $Minutes min)"
        return $true
    }
    Write-Host "[FAIL] $Name"
    return $false
}

$okCount = 0
if (Create-V9Task 'V9_ResolveLoop' 'v9_resolve_loop.py --once' 10) { $okCount++ }
if (Create-V9Task 'V9_CalibrationLoop' 'v9_calibration_loop.py --once' 120) { $okCount++ }
if (Create-V9Task 'V9_ArbiterRecal' 'v9_recalibrate_arbiter.py' 360) { $okCount++ }
if (Create-V9Task 'V9_MetaAgentScan' 'v9_meta_agent_watch.py' 30) { $okCount++ }

Write-Host ""
Write-Host "=== $okCount/4 crons V9 H24 installés ==="
```

## Cron — fonction et fréquence

| Cron | Fréquence | Script | But |
|---|---|---|---|
| `V9_ResolveLoop` | 10 min | `v9_resolve_loop.py --once` | WIN/LOSS auto sur décisions anciennes |
| `V9_CalibrationLoop` | 2h | `v9_calibration_loop.py --once` | stats + principes + analyze |
| `V9_ArbiterRecal` | 6h | `v9_recalibrate_arbiter.py` | propositions pondérations arbiter |
| `V9_MetaAgentScan` | 30 min | `v9_meta_agent_watch.py` | patterns bus (quand émetteurs câblés) |

## Vérification

```powershell
Get-ScheduledTask | Where-Object { $_.TaskName -match 'V9_' } | Select-Object TaskName, State | Format-Table -AutoSize
```

Attendu : 7 tâches V9 (3 existantes + 4 H24), toutes "Ready".

## Désinstallation

```powershell
schtasks /delete /tn "V9_ResolveLoop" /f
schtasks /delete /tn "V9_CalibrationLoop" /f
schtasks /delete /tn "V9_ArbiterRecal" /f
schtasks /delete /tn "V9_MetaAgentScan" /f
```

## Notes

- Les wrappers (v9_resolve_loop.py, v9_calibration_loop.py, etc.) loguent
  dans `logs/v9_<name>_loop.log` (append, idempotent).
- `deliver` Telegram déjà câblé via heartbeat. Les alertes WIN/LOSS
 异常的 ne sont pas du Telegram (Phase future).
- Backlog WIN/LOSS estimé : 58057 décisions au 2026-07-10 02:30 UTC.
  À 990 décisions/batch × 6 batches/heure = 5940 décisions/heure.
  ETA backlog complet : ~10h de cron.
- Aucun cron ne touche `core/v9/*` (R8 respectée).