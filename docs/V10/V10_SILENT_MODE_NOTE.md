# 🔇 V10 — Scripts en mode silencieux (CEO note)

> **Date** : 2026-08-04 06:05 UTC
> **Problème** : fenêtre `V9\.venv\Scripts\python.exe` reste visible
> après lancement des tâches planifiées Windows.

---

## 🎯 Cause racine

Les 2 tâches planifiées qui tournent en boucle infinie :

| Tâche | Script | Avant | Après |
|---|---|---|---|
| `V9CaptureWatchdog` | `v9_capture_watchdog.py` | `python.exe` | **`pythonw.exe`** ✅ |
| `V9SignalAlerter` | `v9_signal_alerter.py` | `python.exe` | **`pythonw.exe`** ✅ |

`python.exe` = console visible
`pythonw.exe` = windowless variant (même Python, pas de terminal attaché)

Le `python.exe` du watchdog lançait lui-même `capture_server` **correctement**
en mode caché (`CREATE_NO_WINDOW` flag), mais le **watchdog lui-même**
gardait une fenêtre visible parce que c'est lui qui était lancé en `python.exe`
par Task Scheduler.

---

## ✅ Patch appliqué (R2 additif pur, 0 destruction)

### Fichiers patchés (4)
- `scripts/install_v9_capture_watchdog_task.ps1` : `python.exe` → `pythonw.exe`
- `scripts/install_v9_signal_alerter_task.ps1` : `python.exe` → `pythonw.exe`
- `scripts/install_v9_learning_cron.ps1` : `python.exe` → `pythonw.exe`
- `scripts/install_v9_telegram_cron.ps1` : `python.exe` → `pythonw.exe`

### Comment ça marche
1. CEO (admin) lance `install_v9_capture_watchdog_task.ps1` en **réinstallant**
   la tâche (le script recrée la tâche à chaque run)
2. Au prochain démarrage de la tâche, Windows lance **`pythonw.exe`** au lieu
   de `python.exe` → **pas de console window visible**
3. Le script continue à tourner normalement (mêmes imports, même comportement)

---

## 🔧 PROCÉDURE POUR ACTIVER LE MODE SILENCIEUX (CEO)

### Option A — Réinstaller les tâches (recommandé, 2 min)

```powershell
# 1. Ouvrir PowerShell en admin
# 2. Réinstaller le watchdog
cd C:\projet\V9
.\scripts\install_v9_capture_watchdog_task.ps1

# 3. Réinstaller l'alerter
.\scripts\install_v9_signal_alerter_task.ps1

# 4. Redémarrer les tâches (optionnel, ou attendre le prochain reboot)
Restart-ScheduledTask -TaskName "V9CaptureWatchdog"
Restart-ScheduledTask -TaskName "V9SignalAlerter"
```

### Option B — Modifier la tâche existante manuellement (sans réinstaller)

```powershell
# 1. PowerShell admin
# 2. Modifier l'action de la tâche pour pointer vers pythonw.exe
$task = Get-ScheduledTask -TaskName "V9CaptureWatchdog"
$task.Actions[0].Execute = "C:\projet\V9\.venv\Scripts\pythonw.exe"
Set-ScheduledTask -InputObject $task
# Idem pour V9SignalAlerter
```

### Option C — Kill la fenêtre actuelle (si encore ouverte)

```powershell
# Identifier le PID de la fenêtre visible
Get-Process python | Where-Object { $_.MainWindowTitle -like "*V9*" }
# Tuer (R0 strict : CEO approval explicite requis)
Stop-Process -Id <PID> -Force
```

---

## 🛡️ Doctrine V10 respectée

- **R1-AGIR** : CEO mandate "met tout les scripts en silencieux", j'agis
- **R2 additif pur** : 4 fichiers patchés (1 ligne chacun), 0 destruction
- **R10-PROTÉGER CAPITAL** : 0 kill, 0 modif runtime (patch prend effet à la prochaine réinstall)
- **R6-EXPLIQUER** : cause racine documentée + procédure claire

---

## 🧪 Tests

- AST validation : 4 fichiers .ps1 non testables en Python (pas de syntaxe Python)
- pytest existant : pas de régression (scripts .ps1, pas de tests Python touchés)
- Commit atomique : 4 fichiers dans 1 commit

---

## 🔖 Note CEO

Une fois la procédure A ou B exécutée, le prochain reboot (ou redémarrage des
tâches) fera disparaître la fenêtre `python.exe` visible. **Pas besoin de
reboot manuel** si tu fais `Restart-ScheduledTask`.

**Action immédiate recommandée** : Option A (2 min, propre).