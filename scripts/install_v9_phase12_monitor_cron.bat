@echo off
REM ============================================================================
REM install_v9_phase12_monitor_cron.bat
REM ----------------------------------------------------------------------------
REM Installe 4 taches planifiees V9_Phase12Monitor_XX qui appellent
REM scripts/v9_phase12_daily_monitor.py --once --alert-telegram --json
REM toutes les 4h (06:00, 10:00, 14:00, 18:00 UTC).
REM
REM Mission : surveillance complete Phase 12 FTMO (walk-forward L7/L8,
REM FTMO validator, health check, kill switches). Alerte Telegram si DRIFT.
REM Idempotent : re-application possible.
REM
REM Usage :
REM   install_v9_phase12_monitor_cron.bat            (applique)
REM   install_v9_phase12_monitor_cron.bat --dry-run  (affiche sans executer)
REM   install_v9_phase12_monitor_cron.bat --remove   (supprime les 4 taches)
REM ============================================================================

setlocal

set "V9_ROOT=C:\projet\V9"
set "PYTHON=%V9_ROOT%\.venv\Scripts\python.exe"
set "LOADER=%V9_ROOT%\scripts\v9_load_kill_switches.py"
set "WRAPPER=%V9_ROOT%\scripts\_run_v9_phase12_monitor.bat"

if /I "%~1"=="-h" goto :help
if /I "%~1"=="--help" goto :help
if /I "%~1"=="/?" goto :help
if /I "%~1"=="--dry-run" goto :dryrun
if /I "%~1"=="--remove" goto :remove

REM 4 taches : 06:00, 10:00, 14:00, 18:00 UTC
for %%H in (06 10 14 18) do (
    set "TASK=V9_Phase12Monitor_%%H"
    set "TR=%WRAPPER%"
    
    schtasks /Delete /TN "%TASK%" /F >nul 2>&1
    
    REM Daily a HH:00 UTC. S4U SYSTEM pour survivre au logoff.
    schtasks /Create /SC DAILY /ST %%H:00 /TN "%TASK%" /TR "%TR%" /F /RL HIGHEST /RU SYSTEM >nul 2>&1
    
    if %ERRORLEVEL% NEQ 0 (
        echo [ERREUR] Echec creation tache %TASK%
        exit /b 1
    )
    
    echo [OK] Tache %TASK% installee (daily %%H:00 UTC, S4U SYSTEM)
)

echo.
echo [OK] 4 taches V9_Phase12Monitor installees (06h/10h/14h/18h UTC)
schtasks /Query /TN "V9_Phase12Monitor_06" /V /FO LIST | findstr /C:"Statut" /C:"Status" /C:"Next Run"
schtasks /Query /TN "V9_Phase12Monitor_10" /V /FO LIST | findstr /C:"Statut" /C:"Status" /C:"Next Run"
schtasks /Query /TN "V9_Phase12Monitor_14" /V /FO LIST | findstr /C:"Statut" /C:"Status" /C:"Next Run"
schtasks /Query /TN "V9_Phase12Monitor_18" /V /FO LIST | findstr /C:"Statut" /C:"Status" /C:"Next Run"
goto :eof

:dryrun
echo [DRY-RUN] 4 taches planifiees qui seraient installees :
echo   V9_Phase12Monitor_06 : daily 06:00 UTC -> %WRAPPER%
echo   V9_Phase12Monitor_10 : daily 10:00 UTC -> %WRAPPER%
echo   V9_Phase12Monitor_14 : daily 14:00 UTC -> %WRAPPER%
echo   V9_Phase12Monitor_18 : daily 18:00 UTC -> %WRAPPER%
echo   Repertoire: %V9_ROOT%
goto :eof

:remove
echo [REMOVE] Suppression des 4 taches V9_Phase12Monitor...
for %%H in (06 10 14 18) do (
    schtasks /Delete /TN "V9_Phase12Monitor_%%H" /F >nul 2>&1
    echo [OK] V9_Phase12Monitor_%%H supprimee
)
goto :eof

:help
echo Usage : install_v9_phase12_monitor_cron.bat [--dry-run | --remove]
exit /b 0