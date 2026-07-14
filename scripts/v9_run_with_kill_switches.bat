@echo off
REM ============================================================================
REM v9_run_with_kill_switches.bat
REM ----------------------------------------------------------------------------
REM Wrapper BAT ultra-simple : delegue tout a v9_load_kill_switches.py
REM (qui charge .env puis exec le sous-process). Utilise par les crons
REM schtasks (install_v9_crons.ps1, install_auto_calibrator_cron.ps1).
REM
REM Origine : motion CEO 2026-07-14 "go Fa debloque Phase 13" (A1+A2).
REM Trace   : DECISIONS_LOG 2026-07-14.
REM
REM Usage :
REM   v9_run_with_kill_switches.bat <script.py> [args...]
REM   v9_run_with_kill_switches.bat -- <script.py> [args...]
REM
REM Doctrine : R8 additif, R18 zero reseau, R25' OFF par defaut.
REM ============================================================================

setlocal

set "V9_ROOT=C:\projet\V9"
set "LOADER=%V9_ROOT%\scripts\v9_load_kill_switches.py"
set "PYTHON=%V9_ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [FATAL] python introuvable: %PYTHON%
    exit /b 2
)

if not exist "%LOADER%" (
    echo [FATAL] helper introuvable: %LOADER%
    exit /b 2
)

REM Si pas d'args, juste verifier que le helper marche
if "%~1"=="" (
    "%PYTHON%" "%LOADER%"
    exit /b %ERRORLEVEL%
)

REM Deleguer : python helper -- <args>
cd /d "%V9_ROOT%"
"%PYTHON%" "%LOADER%" -- %*
exit /b %ERRORLEVEL%
