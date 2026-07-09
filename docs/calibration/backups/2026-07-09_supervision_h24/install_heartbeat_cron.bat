@echo off
REM install_heartbeat_cron.bat — Enregistre le watchdog V9 dans schtasks.
REM
REM À lancer EN ADMINISTRATEUR. Crée 2 tâches :
REM   V9_HeartbeatCheck : toutes les 5 min (check rapide, exit 0/1)
REM   V9_HeartbeatAlert : toutes les 60 min (check + Telegram alive/alert)
REM
REM Aucun code V9 modifié : juste de l'enregistrement Windows.

setlocal

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Privileges administrateur requis.
    echo Clic droit sur install_heartbeat_cron.bat ^> Executer en tant qu'administrateur.
    pause
    exit /b 1
)

set V9_ROOT=D:\Projet\V9
set PYTHON=python

REM === Tâche 1 — check toutes les 5 min ===
schtasks /create ^
    /tn "V9_HeartbeatCheck" ^
    /tr "%PYTHON% %V9_ROOT%\scripts\v9_heartbeat.py --check" ^
    /sc minute ^
    /mo 5 ^
    /rl highest ^
    /f

if %errorlevel% neq 0 (
    echo [ERREUR] Creation V9_HeartbeatCheck a echoue (code %errorlevel%)
    pause
    exit /b 1
)

REM === Tâche 2 — heartbeat toutes les 60 min ===
schtasks /create ^
    /tn "V9_HeartbeatAlert" ^
    /tr "%PYTHON% %V9_ROOT%\scripts\v9_heartbeat.py --heartbeat" ^
    /sc minute ^
    /mo 60 ^
    /rl highest ^
    /f

if %errorlevel% neq 0 (
    echo [ERREUR] Creation V9_HeartbeatAlert a echoue (code %errorlevel%)
    pause
    exit /b 1
)

echo.
echo [OK] 2 taches planifiees enregistrees :
echo   V9_HeartbeatCheck : toutes les 5 min (check rapide)
echo   V9_HeartbeatAlert : toutes les 60 min (Telegram alive/alert)
echo.
echo Verification :
echo   schtasks /query /tn "V9_HeartbeatCheck"
echo   schtasks /query /tn "V9_HeartbeatAlert"
echo.
echo Logs : %V9_ROOT%\logs\heartbeat.log
echo Reset manuel : python %V9_ROOT%\scripts\v9_heartbeat.py --reset
echo.
echo Desinstallation :
echo   schtasks /delete /tn "V9_HeartbeatCheck" /f
echo   schtasks /delete /tn "V9_HeartbeatAlert" /f
echo.

endlocal
pause