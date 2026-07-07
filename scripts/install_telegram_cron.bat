@echo off
REM install_telegram_cron.bat — Enregistre le wrapper Telegram dans schtasks.
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
    echo Clic droit sur install_telegram_cron.bat ^> Executer en tant qu'administrateur.
    pause
    exit /b 1
)

set V9_ROOT=D:\Projet\V9
set BAT_PATH=%V9_ROOT%\scripts\start_telegram_notifier.bat
set TASK_NAME=V9_TelegramNotifier

REM === Vérification que le .bat existe ===
if not exist "%BAT_PATH%" (
    echo [ERREUR] Wrapper introuvable : %BAT_PATH%
    pause
    exit /b 1
)

REM === Création / mise à jour de la tâche planifiée ===
REM /sc onlogon : démarre à chaque login utilisateur
REM /rl highest  : exécute avec les droits max (silencieux, pas de fenêtre)
REM /f           : force l'écrasement si la tâche existe déjà

schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%BAT_PATH%\"" ^
    /sc onlogon ^
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
echo   Decl. : au login
echo   Script: %BAT_PATH%
echo.
echo Verification :
echo   schtasks /query /tn "%TASK_NAME%"
echo.
echo Pour desinstaller :
echo   schtasks /delete /tn "%TASK_NAME%" /f
echo.
echo Note : le wrapper demarre une BOUCLE watchdog (redemarrage toutes
echo les 5 min si crash). Logs dans :
echo   %V9_ROOT%\logs\telegram_notifier.log
echo   %V9_ROOT%\logs\telegram_watchdog.log
echo.

endlocal
pause