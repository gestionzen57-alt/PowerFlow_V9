@echo off
REM ============================================================================
REM install_v9_ftmo_sizing_validator_cron.bat
REM ----------------------------------------------------------------------------
REM Installe la tache planifiee V9_FTMO_SizingValidator qui appelle
REM scripts/v9_ftmo_sizing_validator.py --once --json tous les jours a 06h00 UTC.
REM
REM Mission : validation quotidienne conformite FTMO 10k EUR (risque/trade 1%,
REM DD journalier 5%, DD total 10%). Alerte si NO-GO.
REM Idempotent : re-application possible.
REM
REM Usage :
REM   install_v9_ftmo_sizing_validator_cron.bat            (applique)
REM   install_v9_ftmo_sizing_validator_cron.bat --dry-run  (affiche sans executer)
REM ============================================================================

setlocal

set "V9_ROOT=C:\projet\V9"
set "PYTHON=%V9_ROOT%\.venv\Scripts\python.exe"
set "LOADER=%V9_ROOT%\scripts\v9_load_kill_switches.py"
set "WRAPPER=%V9_ROOT%\scripts\_run_v9_ftmo_sizing_validator.bat"
set "TASK=V9_FTMO_SizingValidator"
set "TR=%WRAPPER%"

if /I "%~1"=="-h" goto :help
if /I "%~1"=="--help" goto :help
if /I "%~1"=="/?" goto :help
if /I "%~1"=="--dry-run" goto :dryrun

schtasks /Delete /TN "%TASK%" /F >nul 2>&1

REM Daily a 06h00 UTC. S4U SYSTEM pour survivre au logoff.
schtasks /Create /SC DAILY /ST 06:00 /TN "%TASK%" /TR "%TR%" /F /RL HIGHEST /RU SYSTEM >nul 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo [ERREUR] Echec creation tache %TASK%
    exit /b 1
)

echo [OK] Tache %TASK% installee (daily 06:00 UTC, S4U SYSTEM)
schtasks /Query /TN "%TASK%" /V /FO LIST | findstr /C:"Statut" /C:"Status" /C:"Next Run"
goto :eof

:dryrun
echo [DRY-RUN] Tache planifiee qui serait installee :
echo   Nom       : %TASK%
echo   Frequence : tous les jours a 06h00 UTC
echo   Commande  : %TR%
echo   Repertoire: %V9_ROOT%
goto :eof

:help
echo Usage : install_v9_ftmo_sizing_validator_cron.bat [--dry-run]
exit /b 0