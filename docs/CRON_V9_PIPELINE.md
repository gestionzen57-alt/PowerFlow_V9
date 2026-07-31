# V9 Pipeline Quotidien — Installation Windows Task Scheduler

**Phase 7 motion CEO « EDGE FUND MAX » 2026-07-28**

## CRON JOB

```powershell
# Ouvrir Task Scheduler
taskschd.msc

# Creer tache basique
$action = New-ScheduledTaskAction -Execute "C:\projet\V9\.venv\Scripts\python.exe" `
    -Argument "C:\projet\V9\scripts\v9_cron_pipeline.py" `
    -WorkingDirectory "C:\projet\V9"

$trigger = New-ScheduledTaskTrigger -Daily -At "02:00"

Register-ScheduledTask -TaskName "V9_PIPELINE_CRON" `
    -Action $action -Trigger $trigger `
    -Description "V9 quotidien: walk_forward + auto_promote_stars + time_exit"
    -User "SYSTEM" -RunLevel Highest
```

## CRON JOB LINUX (si deployer ailleurs)

```cron
# /etc/cron.d/v9_pipeline
0 2 * * * root cd /c/projet/V9 && .venv/bin/python scripts/v9_cron_pipeline.py >> data/v9_cron_pipeline.log 2>&1
```

## CRON JOB HERMES (recommande)

Si Hermes est l'opérateur, créer un cron `cronjob action='create'` via la skill:

```
name: v9-pipeline-quotidien
schedule: 0 2 * * *
prompt: |
  Execute `cd /c/projet/V9 && .venv/Scripts/python.exe scripts/v9_cron_pipeline.py`
  puis `git add reports/ && git commit -m "cron(j7): pipeline quotidien $(date +%Y%m%d)"`
  puis `git push origin feat/v9-foundation-clean`.
  Charge la skill `v9-hedge-fund-autopilot` pour le contexte.
deliver: telegram
```

## SORTIE ATTENDUE

```
=== v9_cron_pipeline START 2026-07-29T02:00:00 ===
walk_forward: 5 fenetres, n_total=300, WR avg=85.0%, total_pips=+2500.0p
auto_promote: 0 promotions, 3 deja presents, written=False
time_exit: 2 forced, 8 skipped, 2 artifact
=== v9_cron_pipeline END ok=True ===
```

## ROLLBACK AUTO

Si `walk_forward.WR_avg < 60%` ET `n_total > 20`, le pipeline :
1. Log un warning `ALERT: walk_forward WR=X% < 60%`
2. Ajoute `result["alert"] = "wr_below_threshold"` dans le dict
3. Ne roll-back PAS automatiquement (motion CEO requise)

Pour un rollback automatique, ajouter dans `v9_cron_pipeline.py` :

```python
if wf_summary.get("wr_avg", 0.0) < 60.0 and wf_summary.get("n_total", 0) > 20:
    # Desactiver V9_MEGA_EDGE_ENABLED
    os.environ["V9_MEGA_EDGE_ENABLED"] = "0"
    # Log l'evenement sur agent_bus
```

## LOGS

Fichier : `C:\projet\V9\data\v9_cron_pipeline.log` (append mode, UTF-8)

Format : `2026-07-29 02:00:00 [INFO] v9.cron_pipeline: walk_forward: ...`

Tail quotidien : `tail -n 50 C:\projet\V9\data\v9_cron_pipeline.log`