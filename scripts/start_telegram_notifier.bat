@echo off
REM start_telegram_notifier.bat — Lance v9_telegram_notifier en mode --watch
REM via pythonw.exe (silencieux, aucune fenêtre qui flashe).
REM
REM Installation (one-shot, en admin) :
REM   schtasks /create /tn "V9_TelegramNotifier" ^
REM     /tr "D:\Projet\V9\scripts\start_telegram_notifier.bat" ^
REM     /sc onlogon /rl highest /f
REM
REM Désinstallation :
REM   schtasks /delete /tn "V9_TelegramNotifier" /f
REM
REM Note : adapter PYTHONW_EXE si Python n'est pas dans C:\Python314\

REM === CONFIGURATION ===
REM Placeholder : remplacer PYTHONW_EXE par le path réel de pythonw.exe
REM sur ta machine. Exemples courants (adapte selon ton install) :
REM   C:\Python314\pythonw.exe
REM   C:\Program Files\Python314\pythonw.exe
set PYTHONW_EXE=C:\Python314\pythonw.exe

set V9_ROOT=D:\Projet\V9
set SCRIPT=%V9_ROOT%\scripts\v9_telegram_notifier.py
set LOG=%V9_ROOT%\logs\telegram_notifier.log
set WDOG_LOG=%V9_ROOT%\logs\telegram_watchdog.log

REM === BOUCLE WATCHDOG ===
REM Redémarre le notifier toutes les 5 min s'il meurt (crash, OOM, etc.).
REM Usage : ce .bat est appelé par schtasks au logon, et NE QUITTE JAMAIS
REM (sauf Ctrl-C manuel). C'est le pattern "always-on minimal" Windows
REM sans dépendance à NSSM / pywin32-service.

:loop
echo [%date% %time%] watchdog: lancement v9_telegram_notifier.py --watch >> "%WDOG_LOG%"
cd /d "%V9_ROOT%"
"%PYTHONW_EXE%" "%SCRIPT%" --watch >> "%LOG%" 2>&1
echo [%date% %time%] watchdog: process termine (exit code %errorlevel%), redemarrage dans 5 min >> "%WDOG_LOG%"
timeout /t 300 /nointerrupt > nul
goto loop