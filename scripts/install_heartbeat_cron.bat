@echo off
REM install_heartbeat_cron.bat — Enregistre le watchdog V9 dans schtasks.
REM
REM À lancer EN ADMINISTRATEUR. Crée 3 tâches :
REM   V9_HeartbeatCheck : toutes les 5 min (check rapide, exit 0/1)
REM   V9_HeartbeatAlert : toutes les 60 min (check + Telegram alive/alert)
REM   V9_AutoRestart    : toutes les 5 min (relance serveur capture si down)
REM
REM Aucun code V9 modifié : juste de l'enregistrement Windows.
REM
REM Chantier 2026-07-09 supervision H24 : ajout V9_AutoRestart (était manquant
REM cf. DECISIONS_LOG 2026-07-09 chantier DB vivante 24/7).
REM
REM Usage :
REM   install_heartbeat_cron.bat            (interactif : pause à la fin)
REM   echo. | install_heartbeat_cron.bat    (silencieux via stdin)
REM
REM Le BAT est "peu bruyant" : il ne pause QUE si stdin est un terminal interactif.
REM En appel automatise (echo. | ou 0<nul) il enchaine les 3 creations sans pause.

setlocal

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERREUR] Privileges administrateur requis.
    echo Clic droit sur install_heartbeat_cron.bat ^> Executer en tant qu'administrateur.
    pause
    exit /b 1
)

REM Chemin résolu dynamiquement (le repo peut être déplacé sans toucher au BAT).
REM Défaut conservé pour les installs standards (D:\Projet\V9) ; sinon
REM l'utilisateur peut surcharger via set V9_ROOT=... avant d'appeler le BAT.
if "%V9_ROOT%"=="" set "V9_ROOT=C:\projet\V9"
set PYTHON=python

REM === Tâche 1 — check toutes les 5 min ===
schtasks /create ^
    /tn "V9_HeartbeatCheck" ^
    /tr "%PYTHON% %V9_ROOT%\scripts\v9_heartbeat.py --check" ^
    /sc minute ^
    /mo 5 ^
    /rl highest ^
    /f

if %errorlevel% neq 0 (
    echo [ERREUR] Creation V9_HeartbeatCheck a echoue (code %errorlevel%)
    pause
    exit /b 1
)

REM === Tâche 2 — heartbeat toutes les 60 min ===
schtasks /create ^
    /tn "V9_HeartbeatAlert" ^
    /tr "%PYTHON% %V9_ROOT%\scripts\v9_heartbeat.py --heartbeat" ^
    /sc minute ^
    /mo 60 ^
    /rl highest ^
    /f

if %errorlevel% neq 0 (
    echo [ERREUR] Creation V9_HeartbeatAlert a echoue (code %errorlevel%)
    pause
    exit /b 1
)

REM === Tâche 3 (NOUVELLE 2026-07-09) — auto-restart toutes les 5 min ===
REM Garantit que le serveur de capture V9 tourne en permanence (VPS H24).
REM Si le serveur est deja actif (PID file + port legitimement occupe), ne fait rien.
REM Sinon, libere le port si stale et relance en arriere-plan, avec alerte Telegram.
schtasks /create ^
    /tn "V9_AutoRestart" ^
    /tr "%PYTHON% %V9_ROOT%\scripts\v9_supervisor.py --autorestart" ^
    /sc minute ^
    /mo 5 ^
    /rl highest ^
    /f

if %errorlevel% neq 0 (
    echo [ERREUR] Creation V9_AutoRestart a echoue (code %errorlevel%)
    pause
    exit /b 1
)

echo.
echo [OK] 3 taches planifiees enregistrees :
echo   V9_HeartbeatCheck : toutes les 5 min (check rapide)
echo   V9_HeartbeatAlert : toutes les 60 min (Telegram alive/alert)
echo   V9_AutoRestart    : toutes les 5 min (relance serveur capture si down)
echo.
echo Verification :
echo   schtasks /query /tn "V9_HeartbeatCheck"
echo   schtasks /query /tn "V9_HeartbeatAlert"
echo   schtasks /query /tn "V9_AutoRestart"
echo.
echo Logs :
echo   %V9_ROOT%\logs\heartbeat.log
echo   %V9_ROOT%\logs\v9_ops.log
echo Reset manuel : python %V9_ROOT%\scripts\v9_heartbeat.py --reset
echo.
echo Desinstallation :
echo   schtasks /delete /tn "V9_HeartbeatCheck" /f
echo   schtasks /delete /tn "V9_HeartbeatAlert" /f
echo   schtasks /delete /tn "V9_AutoRestart" /f
echo.
echo Logs en cas d'investigation :
echo   %V9_ROOT%\logs\heartbeat.log
echo   %V9_ROOT%\logs\v9_ops.log
echo.

endlocal
REM Pas de pause finale : ce BAT est conçu pour être lancé en admin shell.
REM Si lancement en double-clic, l'utilisateur a vu le résultat avant la fermeture
REM de la fenêtre cmd (echo final + exit du process cmd). Silence = succès.