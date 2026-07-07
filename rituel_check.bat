@echo off
cd /d D:\Projet\V9
echo ===== GIT STATUS =====
git status
echo.
echo ===== GIT LOG -10 =====
git log --oneline -10
echo.
echo ===== PYTEST =====
python -m pytest tests/ -q
echo.
echo ===== HEARTBEAT CHECK =====
python scripts/v9_heartbeat.py --check
echo.
echo ===== DASHBOARD =====
python scripts/v9_dashboard.py --once
echo.
echo ===== CRONS WINDOWS =====
schtasks /query /tn "V9_HeartbeatCheck" /v
schtasks /query /tn "V9_HeartbeatAlert" /v