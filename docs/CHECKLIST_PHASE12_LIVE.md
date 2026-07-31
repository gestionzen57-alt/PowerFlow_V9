# CHECKLIST Phase 12 LIVE — Motion CEO « EDGE FUND MAX » 2026-07-31

**Recommandation R4 Perplexity** : formaliser les conditions minimales avant passage LIVE réel.

---

## CONDITIONS BLOQUANTES (à valider AVANT activation V9_EXECUTION_SIMULATION=1)

### 1. Sécurité Telegram (R2)

- [ ] **Rotation des 4 tokens Telegram CEO** (action humaine Søn, bloquante)
  - Raison : 13 jours sans rotation, risque sécurité Phase 12 LIVE
  - Token actuel : `[REDACTED]` (à remplacer dans `scripts/v9_telegram_notifier.py`)
- [ ] Test envoi Telegram OK après rotation
  ```bash
  python scripts/v9_telegram_notifier.py --test
  ```

### 2. Validation live expectancy (R1)

- [ ] **100 trades live paper avec `close_open_trades()` seul** (sans offline)
- [ ] Expectancy live > 0 sur 100 trades
- [ ] Walk-forward quotidien 7j stable (4/4 folds OOS positifs conservés)
- [ ] Note : le walk-forward 31/07 (9469 trades, OOS 5.96p) est sur résolution offline. La vérité live vient de `close_open_trades()` + `ExitSimulator` (≈ breakeven après coûts). Ne pas généraliser le niveau absolu avant run live.

### 3. L3 vs HUMAN_SCALP cohérence (BUG-P4)

- [ ] Décision CEO : L3 time_exit 5min OU HUMAN_SCALP TREND/CASSURE, **PAS les deux**
  - Option A : `V9_DRM_HUMAN_PROFILE_ENABLED=0` → géométrie classique 12/8
  - Option B : `V9_TIME_EXIT_MINUTES=60` pour TREND/CASSURE uniquement
  - Option C : désactiver L3 (`V9_TIME_EXIT_ENABLED=0`)
- [ ] Recommendation : **Option A** (DRM classique) car L3 5min est confirmé (audit SQL, -239p économisés)

### 4. Mirror BLOCKING données humaines (BUG-P2)

- [ ] **Logger au moins 20 trades Søn manuellement** avant activation `V9_HUMAN_MIRROR_BLOCKING=1`
- [ ] CLI : `python scripts/v9_log_human_trade.py --symbol GBPUSD --direction haussiere --timeframe M5 ...`
- [ ] Si < 20 trades, désactiver BLOCKING (`V9_HUMAN_MIRROR_BLOCKING=0`), score=0.5 neutre OK

### 5. Boot alerts (BUG-P1/P2/P4) — Phase 8 livré

- [ ] Module `core/v9/v9_boot_alerts.py` activé au boot du trade_engine
- [ ] 3 alertes vérifiées :
  - `[BUG-P1]` MEGA OFF en prod → warning
  - `[BUG-P2]` Mirror BLOCKING sans données → warning
  - `[BUG-P4]` L3 + HUMAN_SCALP simultanés → warning
- [ ] Test : `pytest tests/test_v9_boot_alerts.py -v` → 8/8 verts

### 6. Kill switches ON (vérification prod)

Avant de lancer LIVE, valider que les kill switches critiques sont ON :

```bash
# Bash/Zsh
grep -E "^V9_(MEGA_EDGE|TIME_EXIT|HUMAN_MIRROR|NO_BAISSIERE|BLACKLIST)" config/v9_kill_switches.env

# Attendu (sans préfixe comment) :
# V9_BLACKLIST_SYMBOLS=USDCAD,AUDUSD,USDJPY,EURUSD,USDCHF
# V9_NO_BAISSIERE=1
# V9_MEGA_EDGE_ENABLED=1
# V9_TIME_EXIT_ENABLED=1
# V9_HUMAN_MIRROR_ENABLED=1
# V9_HUMAN_MIRROR_BLOCKING=0 (ou 1 si 20+ trades loggés)
# V9_DRM_HUMAN_PROFILE_ENABLED=0 (recommandation J7 Option A)
# V9_BAYESIAN_CALIBRATOR_CONSUMER=1
```

### 7. DB backup MD5 (R8)

- [ ] Backup `data/v9_forces.db` avant activation
  ```bash
  cp data/v9_forces.db backups/v9_forces_pre_phase12_$(date +%Y%m%d).db
  md5sum data/v9_forces.db > backups/v9_forces_pre_phase12_$(date +%Y%m%d).md5
  ```
- [ ] Backup `config/calibration_overrides.json` (3 stars ACTIVE)

### 8. MT4 capture_server heartbeat (R3)

- [ ] Vérifier que `core/v9/capture_server.py` reçoit toujours des données (heartbeat < 60s)
- [ ] Ajouter cron heartbeat si manquant (recommandation Perplexity R3)
  - Phase 9 : `scripts/v9_heartbeat_capture.py` + cron 1min
  - Alert Telegram si heartbeat > 5min (capture down)

---

## CONDITIONS NON-BLOQUANTES (à valider APRÈS activation)

### A. Walk-forward quotidien (Phase 7 livré)

- [ ] Cron `scripts/v9_cron_pipeline.py` quotidien 02:00 UTC
- [ ] Si `result["alert"] == "wr_below_threshold"` → motion CEO

### B. Test live 7j paper-trading

- [ ] Trade minimum 30 trades sur 7j avec L1-L9 ON
- [ ] WR live ≥ 60% (sinon rollback motion CEO)
- [ ] Pips cumulés ≥ +200 (sinon rollback motion CEO)
- [ ] Max DD ≤ -100p (sinon rollback motion CEO)

### C. Mirror BLOCKING activation progressive

- [ ] Semaine 1 : `V9_HUMAN_MIRROR_BLOCKING=0` (observateur, log trades Søn)
- [ ] Semaine 2 : si ≥ 20 trades loggés, `V9_HUMAN_MIRROR_BLOCKING=1`
- [ ] Semaine 3 : vérifier que mirror score discriminants (≥ 0.7 = keep, ≤ 0.3 = downgrade)

---

## PROCÉDURE ACTIVATION PHASE 12 LIVE

```bash
# 1. Backup DB
cp data/v9_forces.db backups/v9_forces_pre_phase12_20260731.db
md5sum data/v9_forces.db > backups/v9_forces_pre_phase12_20260731.md5

# 2. Activer V9_EXECUTION_SIMULATION
echo "V9_EXECUTION_SIMULATION=1" >> config/v9_kill_switches.env

# 3. Vérifier boot alerts
python -c "
import os
os.environ['V9_BOOT_CONTEXT'] = 'prod'
from core.v9.v9_boot_alerts import check_kill_switch_coherence
for w in check_kill_switch_coherence():
    print(w)
"

# 4. Désactiver L3 (BUG-P4 fix recommandé)
# OU désactiver HUMAN_SCALP (option A)
sed -i 's/V9_DRM_HUMAN_PROFILE_ENABLED=1/V9_DRM_HUMAN_PROFILE_ENABLED=0/' config/v9_kill_switches.env

# 5. Activer cron walk_forward
# Voir docs/CRON_V9_PIPELINE.md

# 6. Tester live paper 7j
python -m pytest tests/ -q -p no:cacheprovider
.venv/Scripts/python.exe scripts/v9_cron_pipeline.py  # smoke test

# 7. Activer Phase 12 LIVE (mini-lot 0.01 FTMO)
echo "V9_MT4_BRIDGE_ENABLED=1" >> config/v9_kill_switches.env
```

---

## CHECKLIST FINALE PRE-LIVE

- [ ] Sécurité Telegram OK (R2)
- [ ] 100 trades live expectancy > 0 (R1)
- [ ] L3 vs HUMAN_SCALP résolu (BUG-P4)
- [ ] Mirror BLOCKING données humaines ≥ 20 (BUG-P2)
- [ ] Boot alerts testées (BUG-P1/P2/P4)
- [ ] Kill switches vérifiés ON
- [ ] DB backup MD5 créé
- [ ] MT4 heartbeat OK
- [ ] Walk-forward cron installé
- [ ] Tests pytest verts (143/143)

**Si toutes les cases sont cochées → motion CEO Phase 12 LIVE possible.**

---

## POST-LIVE (à surveiller 7j)

- [ ] WR live ≥ 60% (cible)
- [ ] Max DD ≤ -100p
- [ ] Pips cumulés 7j ≥ +200
- [ ] 0 alerte `wr_below_threshold`
- [ ] Telegram notif OK à chaque trade
- [ ] Tokens non exposés (audit logs Telegram)

Si l'un de ces critères tombe, **rollback motion CEO** :
```bash
echo "V9_EXECUTION_SIMULATION=0" > config/v9_kill_switches.env
echo "V9_MT4_BRIDGE_ENABLED=0" >> config/v9_kill_switches.env
```

---

**Document vivant** : update à chaque motion CEO Phase 12. Søn valide, Hermes archive dans `DECISIONS_LOG.md`.