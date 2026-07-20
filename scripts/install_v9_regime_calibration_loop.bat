@echo off
REM ============================================================================
REM install_v9_regime_calibration_loop.bat
REM ----------------------------------------------------------------------------
REM Installe la tache planifiee V9_RegimeCalibrationLoop qui appelle
REM scripts/v9_regime_recalibration_validate.py --all-tf --json toutes les
REM 6 heures, archive les resultats dans data/regime_calibration_history.jsonl
REM pour le suivi de la validation 2 semaines (motion CEO #10 §5).
REM
REM But : mesurer le recalibrage Opus Phase 2 (cable runtime via motion #17)
REM sur 14 jours avant promotion ACTIVE. Les snapshots persistés en DB
REM utilisent encore les legacy seuils ; ce script joue le detecteur en
REM shadow avec les nouveaux seuils et stocke le delta NEUTRE_RATE.
REM
REM Le CEO peut lire data/regime_calibration_history.jsonl pour suivre la
REM convergence et decider de l'activation definitive (decommenter les 6
REM lignes motion #10 dans REGIME_TIMEFRAME_OVERRIDES).
REM
REM Usage :
REM   install_v9_regime_calibration_loop.bat            (applique)
REM   install_v9_regime_calibration_loop.bat --dry-run  (affiche sans executer)
REM ============================================================================

setlocal

set "V9_ROOT=C:\projet\V9"
set "PYTHON=%V9_ROOT%\.venv\Scripts\python.exe"
set "LOADER=%V9_ROOT%\scripts\v9_load_kill_switches.py"
set "BACKUP_DIR=%V9_ROOT%\backups"
set "BACKUP_XML=%BACKUP_DIR%\V9_RegimeCalibrationLoop_original.xml"
set "TASK=V9_RegimeCalibrationLoop"
set "TR=\"%PYTHON%\" -X utf8 \"%LOADER%\" -- scripts\v9_regime_recalibration_validate.py --all-tf --json"

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
schtasks /Delete /TN %TASK% /F 2> nul

echo [INFO] Recreation de %TASK% via le wrapper kill switches (6h)...
schtasks /Create /SC MINUTE /MO 360 /TN %TASK% /TR "%TR%" /RU SYSTEM /RL HIGHEST /F
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
echo [OK ] Tache %TASK% installee (6h). Logs : %V9_ROOT%\logs\v9_ops.log
echo [INFO] Premiere execution : maintenant (dans 1 minute max)
echo [INFO] Test manuel : python scripts\v9_regime_recalibration_validate.py --all-tf --json
exit /b 0

:dryrun
echo [DRY-RUN] Pas de modification.
echo [DRY-RUN] Tache : %TASK%
echo [DRY-RUN] Trigger : %TR%
echo [DRY-RUN] Frequence : toutes les 6 heures (motion CEO #10 §5 validation 2 sem.)
exit /b 0

:help
echo Usage : install_v9_regime_calibration_loop.bat [--dry-run]
exit /b 0
