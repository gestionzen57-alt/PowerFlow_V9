@echo off
REM Wrapper appele par la tache planifiee V9_Phase12Monitor.
REM Necessaire car schtasks /TR ne supporte pas les arguments avec espaces.
"C:\projet\V9\.venv\Scripts\python.exe" -X utf8 "C:\projet\V9\scripts\v9_load_kill_switches.py" -- "C:\projet\V9\scripts\v9_phase12_daily_monitor.py" --once --alert-telegram --json > "C:\projet\V9\logs\v9_phase12_monitor.log" 2>&1