@echo off
REM ============================================================================
REM install_v9_meta_strategy_shadow_cron.bat
REM ----------------------------------------------------------------------------
REM Cree la tache Windows V9_MetaStrategyShadowCron : polling toutes les 5 min
REM du runner scripts/v9_meta_strategy_shadow_cron.py --apply.
REM
REM Le runner lit V9_META_STRATEGY_SHADOW_ENABLED depuis config/v9_kill_switches.env
REM et alimente meta_strategy_shadow_log (R2 additif, table additive) si shadow ON.
REM 100% non-intrusif : lecture seule sur decisions + signals, écriture additive
REM uniquement sur meta_strategy_shadow_log. R25' strict : legacy jamais écrasé.
REM
REM Origine : Chemin C motion CEO 2026-07-21 04h58 UTC (suite NO-GO V1 brief).
REM Trace DECISIONS_LOG §2026-07-21 05h00.
REM
REM Usage :
REM   install_v9_meta_strategy_shadow_cron.bat            (installe la tache)
REM   install_v9_meta_strategy_shadow_cron.bat --dry-run  (affiche sans executer)
REM   install_v9_meta_strategy_shadow_cron.bat --remove   (supprime la tache)
REM ============================================================================

setlocal

set "V9_ROOT=C:\projet\V9"
set "PYTHON=%V9_ROOT%\.venv\Scripts\python.exe"
set "RUNNER=%V9_ROOT%\scripts\v9_meta_strategy_shadow_cron.py"
set "TASK=V9_MetaStrategyShadowCron"
set "TR=\"%PYTHON%\" -X utf8 \"%RUNNER%\" --apply --since 24h --limit 2000"

if /I "%~1"=="--dry-run" goto :dryrun
if /I "%~1"=="/dry-run" goto :dryrun
if /I "%~1"=="--remove" goto :remove
if /I "%~1"=="/remove" goto :remove

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
echo [INFO] Kill switch requis : V9_META_STRATEGY_SHADOW_ENABLED=1 dans config/v9_kill_switches.env
echo [INFO] Premier run : verifier %V9_ROOT%\reports\meta_strategy\ pour shadow logs.
exit /b 0

:dryrun
echo [DRY-RUN] La commande suivante serait executee :
echo   schtasks /Create /SC MINUTE /MO 5 /TN %TASK% /TR "%TR%" /RU SYSTEM /RL HIGHEST /F
exit /b 0

:remove
echo [INFO] Suppression de la tache %TASK%...
schtasks /Delete /TN %TASK% /F
if errorlevel 1 (
    echo [WARN] echec suppression (tache peut-etre absente)
    exit /b 1
)
echo [OK] Tache %TASK% supprimee.
exit /b 0