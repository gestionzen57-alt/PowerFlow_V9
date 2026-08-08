# PLAYBOOK CEO — Promotion S25 → LIVE
**Date** : 2026-08-08 22:10 CEST  
**Statut** : ACTIF dès validation gate

---

## 🎯 Séquence de promotion (dans l'ordre)

### Étape 1 — Valider le gate live
```powershell
make live-gate
# Lit data/live_gate_report.json
# GO = toutes paires G1+G2+G3+G4 verts
```

### Étape 2 — Vérifier circuit-breaker
```powershell
make breaker-status
# Doit retourner : triggered=false
```

### Étape 3 — Vérifier MT5 connecté
```powershell
make mt5
# MT5 doit être ouvert et connecté au broker
```

### Étape 4 — Appliquer migrations SQL
```powershell
make migrate-status
make migrate-apply
# Tables pair_status + walkforward_results doivent exister
```

### Étape 5 — Basculer en LIVE (paire par paire)
```powershell
# Commencer par GBPUSD (meilleur état G1-G4)
python scripts/v10_paper2live.py --pair GBPUSD

# Attendre 24h de données live, puis AUDUSD
python scripts/v10_paper2live.py --pair AUDUSD

# EURUSD et USDJPY : attendre re-run post filtres ICT
```

### Étape 6 — Démarrer monitoring temps réel
```powershell
# Dashboard loop toutes les 5 minutes
python scripts/v10_live_monitor.py --loop 300

# Ou via Makefile
make monitor
```

### Étape 7 — Cron nuit activé automatiquement
```powershell
make cron
# Étape 2 = check MT5
# Étape 8 = resolve outcomes en mode native
# Étape 13 = bilan Telegram
```

---

## 🛑 Procédure d'urgence

| Situation | Action | Commande |
|---|---|---|
| Drawdown > 3% | Circuit-breaker auto | `make breaker-status` |
| 5 pertes consécutives | Alerte Telegram + pause | auto via `v10_live_monitor.py` |
| MT5 déconnecté | Alerte Telegram | auto via cron étape 2 |
| Dérive live vs paper > 15% | Rollback paper | `python v10_paper2live.py --rollback PAIRE` |
| CEO décision manuelle | Reset breaker | `make breaker-reset` |

---

## 📊 État GO/NO-GO paires au 2026-08-08

| Paire | G1 | G2 | G3 | G4 | Verdict | Action |
|---|---|---|---|---|---|---|
| **GBPUSD** | ✅ | ✅ | ⏳ | ✅ | **PRIORITÉ 1** | Basculer en LIVE dès WF OK |
| **AUDUSD** | ✅ | ✅ | ⏳ | ✅ | **PRIORITÉ 2** | Basculer 24h après GBPUSD |
| **EURUSD** | ❌ | ✅ | ⏳ | ⚠️ | **NO-GO** | Re-run post session_filter |
| **USDJPY** | ❌ | ✅ | ⏳ | ✅ | **NO-GO** | Re-run post fix JPY |

---

## 💰 Sizing live initial

| Paire | Lot initial | Max trades/jour | SL max |
|---|---|---|---|
| GBPUSD | 0.01 | 3 | 20 pips |
| AUDUSD | 0.01 | 3 | 20 pips |
| EURUSD | 0.01 | 2 | 15 pips |
| USDJPY | 0.01 | 2 | 20 pips |

> **Règle absolue S25** : Lot 0.01 fixe jusqu'à 50 trades live validés. Puis Kelly fractionnel.

---

## 🔄 Rollback plan

Si performance live < paper de plus de 15% sur 20 trades :
1. `python scripts/v10_paper2live.py --rollback PAIRE`
2. Analyse drift via `v10_live_monitor.py`
3. Re-run shadow 50 trades
4. Re-passer live_gate avant nouvelle promotion

---

*PowerFlow V10 — Playbook CEO S25 — 2026-08-08*
