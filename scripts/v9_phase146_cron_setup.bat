@echo off
REM Phase 146 — Cron audit live vendredi 08/08 18:00 UTC
REM Installe une tache planifiee qui execute scripts/v9_phase146_audit_live.py
REM chaque vendredi a 18:00 UTC (= 20:00 heure Paris ete).

powershell -NoProfile -Command ^
  "if (-not (Get-ScheduledTask -TaskName 'V9Phase146AuditLive' -ErrorAction SilentlyContinue)) {" ^
  "  \$action = New-ScheduledTaskAction -Execute 'C:\projet\V9\.venv\Scripts\python.exe' -Argument '-X utf8 C:\projet\V9\scripts\v9_phase146_audit_live.py'" ^
  "  \$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Friday -At '20:00'" ^
  "  Register-ScheduledTask -TaskName 'V9Phase146AuditLive' -Action \$action -Trigger \$trigger -Description 'Phase 146 audit live GBPUSD (R30/R2 - vendredi 18:00 UTC)'" ^
  "} else {" ^
  "  Write-Host 'V9Phase146AuditLive deja installee'" ^
  "}"
