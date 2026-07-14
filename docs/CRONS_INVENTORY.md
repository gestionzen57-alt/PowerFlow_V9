# Crons Windows V9 — inventaire de référence

> Mis à jour le 2026-07-14 (audit ZCode). Source de vérité pour les tâches planifiées V9.

## Crons installés (10, tous Ready)

Vérifier : `Get-ScheduledTask | Where-Object { $_.TaskName -match 'V9_' }`

| Cron | Fréquence | Script cible | But | Installateur |
|---|---|---|---|---|
| `V9_AutoRestart` | 5 min | `v9_supervisor.py --autorestart` | Relance capture_server si down | `install_v9_crons.ps1` |
| `V9_HeartbeatCheck` | 5 min | `v9_heartbeat.py --check` | DB freshness + port 31685 | `install_v9_crons.ps1` |
| `V9_HeartbeatAlert` | 60 min | `v9_heartbeat.py --heartbeat` | Alerte Telegram si problème | `install_v9_crons.ps1` |
| `V9_ResolveLoop` | 10 min | `v9_resolve_loop.py --once` | WIN/LOSS auto sur décisions anciennes | `install_h24_crons.ps1` |
| `V9_CalibrationLoop` | 2h | `v9_calibration_loop.py --once` | Stats + principes + analyze | `install_h24_crons.ps1` |
| `V9_ArbiterRecal` | 6h | `v9_recalibrate_arbiter.py` | Propositions pondérations arbiter | `install_h24_crons.ps1` |
| `V9_MetaAgentScan` | 30 min | `v9_meta_agent_watch.py` | Patterns bus (quand émetteurs câblés) | `install_h24_crons.ps1` |
| `V9_LearningLoop` | 23h00 quotidien | `v9_ops.py propose 7` | Boucle apprentissage (learning_proposals) | `install_v9_learning_cron.ps1` |
| `V9_AutoCalibrator` | 03h00 quotidien | `v9_auto_calibrator.py --once` | Recalibrage automatique (propose-only) | `install_missing_crons.ps1` |
| `V9_TelegramAgent` | au login | `v9_telegram_notifier.py --watch` | Notifier Telegram (boucle watchdog) | `install_missing_crons.ps1` |

## Crons à installer (aucun — tous installés)

Tous les 10 crons V9 sont installés et Ready. Vérifier :
```powershell
Get-ScheduledTask | Where-Object { $_.TaskName -match 'V9_' } | Select-Object TaskName, State
```

## Notes

- Les wrappers `run_*.bat` orphelins ont été supprimés (audit 2026-07-14) — les
  schtasks pointent directement vers `.venv\Scripts\python.exe scripts\...`.
- `install_telegram_cron.bat`, `install_daily_report_cron.bat`,
  `install_heartbeat_cron.bat` supprimés (doublons des `.ps1`, chemins `D:\` obsolètes).
- `install_v9_crons_fixed.bat` supprimé (doublon de `install_v9_crons.ps1`).