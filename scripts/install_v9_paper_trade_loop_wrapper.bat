@echo off
REM ============================================================================
REM install_v9_paper_trade_loop_wrapper.bat
REM ----------------------------------------------------------------------------
REM Refit de la tache V9_PaperTradeLoop pour qu'elle passe par
REM v9_load_kill_switches.py (charge config/v9_kill_switches.env AVANT d'exec
REM le supervisor). Corrige P0.4 : le cron actuel lance le supervisor SANS
REM charger le .env, donc loop_breaker / no_baissiere etc. etaient lus OFF.
REM
REM Etapes :
REM   1. Backup de la tache actuelle -> backups/V9_PaperTradeLoop_original.xml
REM   2. Delete + Recreate via le wrapper de chargement kill switches.
REM
REM Origine : pre-reouverture 2026-07-19 (audit edgefund, P0.4/P0.5). DECISIONS_LOG.
REM
REM Usage :
REM   install_v9_paper_trade_loop_wrapper.bat            (applique)
REM   install_v9_paper_trade_loop_wrapper.bat --dry-run  (affiche sans executer)
REM ============================================================================

setlocal

set "V9_ROOT=C:\projet\V9"
set "PYTHON=%V9_ROOT%\.venv\Scripts\python.exe"
set "LOADER=%V9_ROOT%\scripts\v9_load_kill_switches.py"
set "BACKUP_DIR=%V9_ROOT%\backups"
set "BACKUP_XML=%BACKUP_DIR%\V9_PaperTradeLoop_original.xml"
set "TASK=V9_PaperTradeLoop"
set "TR=\"%PYTHON%\" -X utf8 \"%LOADER%\" -- scripts\v9_supervisor.py --paper-trade"

if /I "%~1"=="--dry-run" goto :dryrun
if /I "%~1"=="/dry-run" goto :dryrun

if not exist "%PYTHON%" (
    echo [FATAL] python introuvable: %PYTHON%
    exit /b 2
)
if not exist "%LOADER%" (
    echo [FATAL] loader introuvable: %LOADER%
    exit /b 2
)
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

echo [INFO] Backup de la tache actuelle -> %BACKUP_XML%
schtasks /Query /TN %TASK% /XML > "%BACKUP_XML%" 2>nul
if errorlevel 1 (
    echo [WARN] Tache %TASK% introuvable (rien a sauvegarder) - on continue.
)

echo [INFO] Suppression de l'ancienne tache %TASK%...
schtasks /Delete /TN %TASK% /F 2>nul

echo [INFO] Recreation de %TASK% via le wrapper kill switches (5 min)...
schtasks /Create /SC MINUTE /MO 5 /TN %TASK% /TR "%TR%" /RU SYSTEM /RL HIGHEST /F
if errorlevel 1 (
    echo [FATAL] echec recreation tache %TASK%
    exit /b 1
)

echo [INFO] Verification...
schtasks /Query /TN %TASK%
echo [OK] Tache %TASK% refit via wrapper. Backup: %BACKUP_XML%
exit /b 0

:dryrun
echo [DRY-RUN] Les commandes suivantes seraient executees :
echo   schtasks /Query /TN %TASK% /XML ^> "%BACKUP_XML%"
echo   schtasks /Delete /TN %TASK% /F
echo   schtasks /Create /SC MINUTE /MO 5 /TN %TASK% /TR "%TR%" /RU SYSTEM /RL HIGHEST /F
exit /b 0
