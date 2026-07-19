@echo off
REM ============================================================================
REM install_v9_live_watchdog_cron.bat
REM ----------------------------------------------------------------------------
REM Cree la tache Windows V9_LiveWatchdogLoop : lance le runner watchdog live
REM toutes les 5 minutes (scripts/v9_live_watchdog_run.py --alert-telegram --json).
REM
REM Le runner lit V9_LIVE_WATCHDOG_ENABLED depuis config/v9_kill_switches.env
REM (via core.v9.kill_switches). Lecture seule stricte DB. R30 : recommande,
REM ne mute pas (pas de --apply-recommendations dans le cron).
REM
REM Origine : pre-reouverture 2026-07-19 (audit edgefund, P0.2). Trace DECISIONS_LOG.
REM
REM Usage :
REM   install_v9_live_watchdog_cron.bat            (installe la tache)
REM   install_v9_live_watchdog_cron.bat --dry-run  (affiche sans executer)
REM ============================================================================

setlocal

set "V9_ROOT=C:\projet\V9"
set "PYTHON=%V9_ROOT%\.venv\Scripts\python.exe"
set "RUNNER=%V9_ROOT%\scripts\v9_live_watchdog_run.py"
set "TASK=V9_LiveWatchdogLoop"
set "TR=\"%PYTHON%\" -X utf8 \"%RUNNER%\" --alert-telegram --json"

if /I "%~1"=="--dry-run" goto :dryrun
if /I "%~1"=="/dry-run" goto :dryrun

if not exist "%PYTHON%" (
    echo [FATAL] python introuvable: %PYTHON%
    exit /b 2
)
if not exist "%RUNNER%" (
    echo [FATAL] runner introuvable: %RUNNER%
    exit /b 2
)

echo [INFO] Creation de la tache %TASK% (toutes les 5 min)...
schtasks /Create /SC MINUTE /MO 5 /TN %TASK% /TR "%TR%" /RU SYSTEM /RL HIGHEST /F
if errorlevel 1 (
    echo [FATAL] echec creation tache %TASK%
    exit /b 1
)

echo [INFO] Verification...
schtasks /Query /TN %TASK%
echo [OK] Tache %TASK% installee.
exit /b 0

:dryrun
echo [DRY-RUN] La commande suivante serait executee :
echo   schtasks /Create /SC MINUTE /MO 5 /TN %TASK% /TR "%TR%" /RU SYSTEM /RL HIGHEST /F
exit /b 0
