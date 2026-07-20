@echo off
REM ============================================================================
REM install_v9_resolve_decision_loop.bat
REM ----------------------------------------------------------------------------
REM Installe la tache planifiee V9_ResolveDecisionLoop qui appelle le daemon
REM `v9_resolve_decision_auto_daemon.py --once` toutes les 5 minutes.
REM
REM Contexte (incident 2026-07-20 13h55 UTC) :
REM   Le daemon n'etait PAS schedule. ~70k decisions `preparer_entree` non
REM   resolues bloquees, donc TradeEngine.close_open_trades() ne pouvait pas
REM   fermer les paper_trades ouverts (filtre `d.is_win IS NOT NULL`).
REM   8 paper_trades GBPUSD/AUDUSD/USDJPY/USDCHF bloques 3h avant cloture.
REM
REM Complement du fix R2 additif `scripts/_resolve_pending.py` appele par
REM V9_PaperTradeLoop. Cette tache ajoute un filet de securite dedie (5 min)
REM au cas ou V9_PaperTradeLoop n'aurait pas tourne (panne supervisor).
REM
REM Etapes :
REM   1. Backup de la tache actuelle (si existe) -> backups/V9_ResolveDecisionLoop_original.xml
REM   2. Delete + Recreate la tache planifiee (5 min, SYSTEM)
REM
REM Usage :
REM   install_v9_resolve_decision_loop.bat            (applique)
REM   install_v9_resolve_decision_loop.bat --dry-run  (affiche sans executer)
REM ============================================================================

setlocal

set "V9_ROOT=C:\projet\V9"
set "PYTHON=%V9_ROOT%\.venv\Scripts\python.exe"
set "LOADER=%V9_ROOT%\scripts\v9_load_kill_switches.py"
set "BACKUP_DIR=%V9_ROOT%\backups"
set "BACKUP_XML=%BACKUP_DIR%\V9_ResolveDecisionLoop_original.xml"
set "TASK=V9_ResolveDecisionLoop"
set "TR=\"%PYTHON%\" -X utf8 \"%LOADER%\" -- scripts\v9_resolve_decision_auto_daemon.py --once --backup backups\resolve_pending_auto --no-require-capture --json"

if /I "%~1"=="-h" goto :help
if /I "%~1"=="--help" goto :help
if /I "%~1"=="/?" goto :help
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

echo [INFO] Backup de la tache actuelle (si existe) -^> %BACKUP_XML%
schtasks /Query /TN %TASK% /XML 1> "%BACKUP_XML%" 2> nul
if errorlevel 1 (
    echo [WARN] Tache %TASK% introuvable (rien a sauvegarder) - on continue.
)

echo [INFO] Suppression de l'ancienne tache %TASK%...
schtasks /Delete /TN %TASK% /F 2^> nul

echo [INFO] Recreation de %TASK% via le wrapper kill switches (5 min)...
schtasks /Create /SC MINUTE /MO 5 /TN %TASK% /TR "%TR%" /RU SYSTEM /RL HIGHEST /F
if errorlevel 1 (
    echo [FATAL] echec recreation tache %TASK%
    exit /b 1
)

echo [INFO] Verification...
schtasks /Query /TN %TASK% /V | findstr /C:"%TASK%"
if errorlevel 1 (
    echo [FATAL] tache %TASK% non trouvee apres creation
    exit /b 1
)

echo.
echo [OK ] Tache %TASK% installee (5 min). Logs : %V9_ROOT%\logs\v9_resolve_daemon.log
echo [INFO] Premiere execution : maintenant (dans 1 minute max)
echo [INFO] Test manuel : python scripts\v9_resolve_decision_auto_daemon.py --once --backup backups\resolve_pending_auto --no-require-capture --json
exit /b 0

:dryrun
echo [DRY-RUN] Pas de modification.
echo [DRY-RUN] Tache : %TASK%
echo [DRY-RUN] Trigger : %TR%
echo [DRY-RUN] Frequence : toutes les 5 minutes
exit /b 0

:help
echo Usage : install_v9_resolve_decision_loop.bat [--dry-run]
exit /b 0
