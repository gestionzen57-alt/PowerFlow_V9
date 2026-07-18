# Checklist pré-réactivation dimanche 2026-07-19 21h UTC

> **Créé le** : 2026-07-18 15h15 UTC
> **Mis à jour** : 2026-07-18 15h22 UTC (capture_server + crons déjà actifs)
> **Motion CEO** : « Go Audit DB Option B + Réactiver capture_server + 7 crons gelés dimanche 21h UTC (1h avant réouverture) »
> **Référence** : `workspace/perplexity/memory/DECISIONS_LOG.md` §2026-07-18 « Motion CEO audit Option B + réactivation 21h UTC » + « CORRECTIF capture_server déjà actifs »
> **Statut** : ⚠️ Partiellement devancé — pipeline techniquement actif depuis 12-15h UTC, mais aucune donnée fraîche. Vérification dimanche 21h UTC critique.

---

## 🎯 Objectif

Réactiver proprement le pipeline V9 avant la réouverture du marché Forex dimanche 2026-07-19 22h UTC :
1. Audit DB Option B déjà appliqué à 12h UTC (DB live = 2.6 GiB, −303 MiB, 1 680 902 shadow triggered=0 purgées)
2. Redémarrer `capture_server` (PID 12936 actuellement arrêté, port 31685)
3. Réactiver les 7 crons V9 gelés depuis l'audit P0-P2
4. Vérifier que tout fonctionne avant la réouverture (T+60 min = 22h UTC)

---

## 📋 Pré-réactivation (dimanche 20h30 UTC — 30 min avant)

### Étape 1 — Vérifier l'état DB

```bash
cd C:/projet/V9

# Vérifier taille DB et compteurs
python -c "
import sqlite3
conn = sqlite3.connect('data/v9_forces.db')
print('DB size:', round(__import__('os').path.getsize('data/v9_forces.db') / 1e9, 3), 'GiB')
print('journal_mode:', conn.execute('PRAGMA journal_mode').fetchone()[0])
print('principle_evaluations:', conn.execute('SELECT COUNT(*) FROM principle_evaluations').fetchone()[0])
print('shadow triggered=0:', conn.execute(\"SELECT COUNT(*) FROM principle_evaluations WHERE source_type='shadow' AND triggered=0\").fetchone()[0])
print('forces_snapshots (last hour):', conn.execute(\"SELECT COUNT(*) FROM forces_snapshots WHERE timestamp > datetime('now', '-1 hour')\").fetchone()[0])
"

# Attendu :
# DB size: ~2.6 GiB
# journal_mode: wal
# principle_evaluations: 924308
# shadow triggered=0: 0  (preuve Option B appliquée)
# forces_snapshots (last hour): 0  (marché fermé, normal)
```

### Étape 2 — Vérifier l'absence de capture_server

```bash
tasklist //FI "IMAGENAME eq python.exe" //FO CSV 2>&1 | grep -i "capture_server"
# Attendu : vide (sinon conflit port 31685)

netstat -ano | findstr ":31685"
# Attendu : vide
```

### Étape 3 — Vérifier MT4 EA (côté Windows VPS)

- Ouvrir MT4 sur le VPS (RDP ou session locale)
- Vérifier que l'EA `V9_Sonde_TF` + `V9_Sonde_M1` est chargé sur GBPUSD M15
- Vérifier que `Experts` log ne montre pas d'erreur récente
- **Si MT4 pas chargé** → ⚠️ NE PAS réactiver les crons, le pipeline sera muet

---

## 🚀 Réactivation (dimanche 21h00 UTC — 1h avant ouverture)

### Étape 4 — Lancer capture_server (R28-safe, motion CEO enregistrée)

```bash
cd C:/projet/V9

# Option 1 : foreground (recommandé pour debug)
python -m core.v9.capture_server

# Option 2 : background via v9_ops
python scripts/v9_ops.py start
```

**Vérification** (T+30s) :
```bash
netstat -ano | findstr ":31685"
# Attendu : LISTENING sur port 31685

curl http://127.0.0.1:31685/test
# Attendu : {"status": "ok", "uptime_seconds": 30, ...}
```

### Étape 5 — Réactiver les 7 crons V9 gelés

```powershell
# Crons gelés depuis l'audit P0-P2 (12h UTC aujourd'hui)
schtasks /Change /ENABLE /TN "V9_CalibrationLoop"
schtasks /Change /ENABLE /TN "V9_MetaAgentScan"
schtasks /Change /ENABLE /TN "V9_ResolveLoop"
schtasks /Change /ENABLE /TN "V9_PaperTradeLoop"
schtasks /Change /ENABLE /TN "V9_StrategyPoleRecompute"
schtasks /Change /ENABLE /TN "V9_HeartbeatCheck"
schtasks /Change /ENABLE /TN "V9_AutoRestart"
```

**Crons à NE PAS toucher** (déjà actifs ou dangereux) :
- `V9CaptureWatchdog` — peut redémarrer capture_server spontanément ⚠️ à surveiller
- `V9_ArbiterRecal` (15h05) — déjà actif
- `V9_AutoCalibrator` (03h00) — déjà actif
- `V9_LearningLoop` (23h00) — déjà actif
- `V9_HeartbeatAlert` (12h04) — déjà actif

### Étape 6 — Snap T+0 métriques

```bash
# Vérifier que des snapshots frais arrivent (MT4 doit envoyer)
sleep 60
python -c "
import sqlite3
conn = sqlite3.connect('data/v9_forces.db')
n = conn.execute(\"SELECT COUNT(*) FROM forces_snapshots WHERE timestamp > datetime('now', '-1 minute')\").fetchone()[0]
print(f'snapshots last 1 min: {n}')
print('Attendu: > 0 (MT4 envoie en temps réel)')
"

# Vérifier que le pipeline tourne
python -c "
import sqlite3
conn = sqlite3.connect('data/v9_forces.db')
print('decisions last 5 min:', conn.execute(\"SELECT COUNT(*) FROM decisions WHERE timestamp > datetime('now', '-5 minute')\").fetchone()[0])
print('signals last 5 min:', conn.execute(\"SELECT COUNT(*) FROM signals WHERE timestamp > datetime('now', '-5 minute')\").fetchone()[0])
print('paper_trades last 5 min:', conn.execute(\"SELECT COUNT(*) FROM paper_trades WHERE opened_at > datetime('now', '-5 minute')\").fetchone()[0])
"
```

### Étape 7 — Alerte Telegram

Si T+60s on a `snapshots last 1 min > 0` → envoyer Telegram à Søn :
```
✅ Pipeline V9 réactivé — T+60s après motion CEO
DB : 2.6 GiB (Option B appliquée)
7 crons : réactivés
Capture_server : OK (port 31685)
Marché Forex : rouvre dans 1h
```

Sinon → alerter Hermès + Søn immédiatement :
```
⚠️ Pipeline V9 réactivé MAIS aucune donnée fraîche
MT4 EA peut-être non chargé
Action : vérifier MT4 sur VPS avant 22h UTC
```

---

## 🛡️ Garde-fous (R6, R28)

- **R28** : motion CEO explicite enregistrée dans `DECISIONS_LOG.md` AVANT exécution ✅
- **R6** : si une étape échoue, **STOP** et alerter avant de continuer
- **Pas de motion CEO additionnelle** : si un imprévu survient (DB corrompue, MT4 absent, etc.), **arrêt immédiat + alerte Telegram** plutôt que motion usurpée
- **Kill switch d'urgence** : si DD > -500 pips sur T+24h → `V9_TRADER_MINI_ENABLED=0` + alerte CEO

---

## 📊 Métriques attendues T+24h (lundi 21h UTC)

| Métrique | Cible | Source |
|---|---|---|
| snapshots last 1h (T+24h) | > 0 | DB live |
| decisions last 24h | > 50 | DB live |
| paper_trades last 24h | > 5 | DB live |
| WR paper_trades | > 80 % | DB live |
| Brier calibrated (Phase E) | < 0.13 | `data/v9_calibration.db` |
| Max DD | < -300 pips | `paper_trades` |

---

## 📞 Contacts

- **Hermès** (M3) : brief dans `workspace/perplexity/BRIEF_HERMES_HONNETE_20260718.md`
- **Søn** (CEO) : motion CEO dans `DECISIONS_LOG.md`
- **Telegram** : envoyer via `python scripts/v9_telegram_notifier.py --send-text "message"`

---

*Checklist rédigé le 2026-07-18 par ZCode, à la demande de Søn.*
*Motion CEO « Go audit Option B + réactivation 21h UTC » — R28 strict, R6 défensif.*
*Dimanche 21h UTC = exécution. D'ici là : repos et patience.*
