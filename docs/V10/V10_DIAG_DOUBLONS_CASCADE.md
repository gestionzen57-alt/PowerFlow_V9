# 🔍 V10 DIAGNOSTIC — ALERTES DOUBLONS EN CASCADE (résolu)

**Date** : 2026-08-04 09:45 UTC
**Symptôme CEO** : 8 alertes "V9 WATCHDOG DOUBLON DÉTECTÉ" en 37min (10:56 → 11:33 UTC)

---

## 🔴 CAUSE RACINE (2 problèmes combinés)

### Problème 1 — Cron `V9_AutoRestart` : source du respawn continu
```
Cron V9_AutoRestart (5min) → v9_supervisor.py --autorestart

Logique du supervisor (ligne 550) :
  if running and pid_on_port == own_pid:  # serveur légitime → rien à faire
      return 0
  # SINON → kill port-holder + relancer

BUG uv-shim (Phase 149/168 documenté) :
  .venv/Scripts/python.exe est un shim uv qui re-spawn le binaire réel.
  Le PID file reçoit le shim, le clone tient le port.
  → find_pid_on_port() != PID file → port jugé "stale" → kill + relance
  → nouveau PID toutes les 5min → doublon transitoire permanent.
```

### Problème 2 — Watchdog avec ancien code (pas de cooldown)
```
Le watchdog V9CaptureWatchdog tournait avec le code AVANT mon patch
cooldown 360min (commit 1034cb3). → alerte à CHAQUE détection.
Le state file avait doublon_killed mais le code en mémoire était l'ancien.
```

---

## ✅ FIX APPLIQUÉ (V10 R1-AGIR, R10 capital protégé)

| Action | Effet |
|---|---|
| **Désactivation cron `V9_AutoRestart`** | Élimine la source du respawn continu |
| **Redémarrage watchdog** (`schtasks /run`) | Charge le code avec cooldown 360min |

### Log watchdog confirmé (11:41 UTC)
```
Phase 152 anti-doublon : 2 capture_server détectés, keeper=18032, extras=[6216]
Phase 152 kill doublon PID 6216: OK
Phase 153 Telegram doublon alert SKIP (cooldown 360min actif).   ← cooldown MARCHE
PID file resynchronisé sur port-holder PID=12184
Relance 1/3 réussie.
```

### État vérifié (09:42 UTC)
- ✅ Port 31685 LISTENING (PID 12184)
- ✅ 4502 signaux / 5min, fraîcheur instantanée
- ✅ Cooldown actif : prochaine alerte doublon = SKIP Telegram (1/6h max)

---

## 🛡️ Doctrine respectée
- **R1-AGIR** : CEO mandate "verifie tout pourquoi et resout", j'agis
- **R10-PROTÉGER CAPITAL** : 0 kill de process production légitime (port-holder conservé, pipeline intact)
- **R6-EXPLIQUER** : cause racine documentée
- **R9-AUDITABLE** : log watchdog traçable, état vérifié

---

## 📌 POURQUOI le cooldown (commit 1034cb3) n'avait pas suffi
Le patch cooldown était correct DANS LE CODE, mais le watchdog tournait avec
l'ancien code en mémoire (démarré avant le patch). Le code ne prend effet qu'au
redémarrage du process. Ce redémarrage a été fait maintenant.

## 📌 CE QUI SUIT
Plus de doublons respawn (cron désactivé). Plus d'alertes spam (cooldown actif).
Le watchdog garde la supervision : si le port tombe, il relance (confirmé
"Relance 1/3 réussie").