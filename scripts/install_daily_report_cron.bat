@echo off
REM install_daily_report_cron.bat — Enregistre v9_daily_report.py en cron quotidien.
REM
REM À lancer EN ADMINISTRATEUR (un seul clic droit > Exécuter en administrateur).
REM Le .bat vérifie les privilèges et affiche la commande sinon.
REM
REM Aucun code V9 modifié : juste de l'enregistrement Windows.

setlocal

REM === Vérification privilèges admin ===
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Ce script necessite les privileges administrateur.
    echo Clic droit sur install_daily_report_cron.bat ^> Executer en tant qu'administrateur.
    pause
    exit /b 1
)

set V9_ROOT=D:\Projet\V9
set PYTHON_EXE=C:\Python314\python.exe
set SCRIPT=%V9_ROOT%\scripts\v9_daily_report.py
set TASK_NAME=V9_DailyReport

REM === Vérification que le script existe ===
if not exist "%SCRIPT%" (
    echo [ERREUR] Script introuvable : %SCRIPT%
    pause
    exit /b 1
)

REM === Création / mise à jour de la tâche planifiée ===
REM /sc daily /st 23:00 : tous les jours à 23h00
REM /rl highest      : droits max (lecture DB + logs)
REM /f               : force l'écrasement si la tâche existe

schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%PYTHON_EXE%\" \"%SCRIPT%\" --no-color > \"%V9_ROOT%\logs\daily_report.log\" 2>&1" ^
    /sc daily ^
    /st 23:00 ^
    /rl highest ^
    /f

if %errorlevel% neq 0 (
    echo [ERREUR] schtasks /create a echoue (code %errorlevel%)
    pause
    exit /b 1
)

echo.
echo [OK] Tache planifiee enregistree :
echo   Nom   : %TASK_NAME%
echo   Decl. : tous les jours a 23:00
echo   Comm. : %PYTHON_EXE% %SCRIPT% --no-color
echo.
echo Verification :
echo   schtasks /query /tn "%TASK_NAME%"
echo.
echo Pour desinstaller :
echo   schtasks /delete /tn "%TASK_NAME%" /f
echo.
echo Test immediat (sans attendre 23h) :
echo   python %SCRIPT% --no-color
echo.

endlocal
pause