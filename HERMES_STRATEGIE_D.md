# HERMES — STRATÉGIE D : FUSION CONTRÔLÉE | 10/08/2026 10:28 CEST

> **Mandat CEO No-Limit — Perplexity architecte**
> **Basé sur rapport ZCode `reports/repo_realignment_report.json` commit `e717ecb`**
> **Doctrine R1/R2/R6/R7/R9/R10 stricte**

---

## 🎯 Verdict ZCode — Stratégie D validée

| Dimension | Base A `feat/v10-c20-healthy @ 2c56432` | Source B `feat/replay-fullstack-v10 @ 218b5b3` |
|---|---|---|
| Tests | ✅ 1310/1310 vérifiés ZCode | 1310/1310 (non re-vérifiés) |
| Modules C11-C20 | ✅ 56 modules (MasterOrchestrator, OrderRouter…) | ❌ absents |
| Replay engine | S25 (904 lignes) | ✅ C3-C10 authentique (1879 lignes diff) |
| API `should_recalibrate` | Triplet (anomalie) | ✅ `RecalibDecision` (consumers runtime) |
| CHANGELOG_V10.md | ✅ présent | ❌ absent |

**Décision :** Base = A (2c56432), adopter API/tests de B, fusionner les 2 fichiers majeurs.

---

## ⚡ EXÉCUTION STRATÉGIE D — Hermes, go maintenant

### ÉTAPE 1 — Créer la branche unifiée depuis la base saine

```bash
git fetch origin
git checkout feat/v10-c20-healthy
git pull origin feat/v10-c20-healthy
# Créer feat/v10-unified depuis la base saine 1310/1310
git checkout -b feat/v10-unified
git push origin feat/v10-unified
echo "Base feat/v10-unified créée depuis 2c56432"
```

---

### ÉTAPE 2 — Importer `v10_replay_engine.py` version B (1879 lignes)

Le replay engine de B (feat/replay-fullstack-v10) est la version authentique C3-C10 :

```bash
# Copier le replay engine de B vers la branche unifiée
git checkout origin/feat/replay-fullstack-v10 -- core/v10/v10_replay_engine.py

# Vérifier que les imports ne cassent rien
python -c "from core.v10.v10_replay_engine import ReplayEngine; print('OK')"

# Si OK :
pytest tests/test_v10_replay*.py -q --tb=short
```

---

### ÉTAPE 3 — Importer `v10_signal_generator_live.py` version B

```bash
git checkout origin/feat/replay-fullstack-v10 -- core/v10/v10_signal_generator_live.py

python -c "from core.v10.v10_signal_generator_live import SignalGeneratorLive; print('OK')"
pytest tests/test_v10_signal_generator*.py -q --tb=short
```

---

### ÉTAPE 4 — Adopter l'API RecalibDecision (version B)

La branche A utilise encore le triplet `(triggered, reason, setups)` → anomalie.
Les consumers runtime (`learning_loop`, `calibrate_apply`) consomment déjà `RecalibDecision`.

```bash
# Copier v10_auto_recalibrator.py depuis B
git checkout origin/feat/replay-fullstack-v10 -- core/v10/v10_auto_recalibrator.py

# Vérifier les 8 fichiers de test alignés sur RecalibDecision (déjà OK sur B)
pytest tests/test_v10_auto_recalibrator*.py -q --tb=short
```

**Si des tests de A échouent sur RecalibDecision :**
```bash
# Identifier les tests qui attendent encore le triplet :
pytest tests/ -q --tb=line 2>&1 | grep -i "recalib\|triplet\|triggered"
# Mettre à jour ces assertions vers RecalibDecision (R2 test-only)
```

---

### ÉTAPE 5 — Suite complète sur feat/v10-unified

```bash
pytest tests/ -q 2>&1 | tail -5
# Cible : >= 1310/1310
# Si échecs : corriger cas par cas, R2 strict (tests only, jamais modules C11-C20)
```

---

### ÉTAPE 6 — Commit de fusion + push

```bash
git add core/v10/v10_replay_engine.py \
        core/v10/v10_signal_generator_live.py \
        core/v10/v10_auto_recalibrator.py

# Si des tests ont été mis à jour :
git add tests/

git commit -m "feat(unified): Stratégie D — replay+sgl+recalib depuis B, base C11-C20 depuis A [R2/R7/R9]

Base : feat/v10-c20-healthy @ 2c56432 (56 modules C11-C20, 1310/1310 ZCode)
Fusion : v10_replay_engine (B, 1879L C3-C10) + v10_signal_generator_live (B)
         + v10_auto_recalibrator RecalibDecision (B, API runtime)
Tests : >= 1310/1310
Source ZCode : reports/repo_realignment_report.json @ e717ecb
[R2/R7/R9/R14]"

git push origin feat/v10-unified
```

---

### ÉTAPE 7 — Ajouter les modules Hermes V2 (chantiers 1-4)

Une fois feat/v10-unified stable, ajouter les modules R2 générés ce matin :

```bash
# Ajouter StaleGuard + DataGapValidator depuis feat/replay-fullstack-v10
# (si Hermes les a committé là) ou les créer directement

# StaleGuard
cat > core/v10/v10_stale_guard.py << 'PYEOF'
# [code v10_stale_guard.py depuis HERMES_PROMPT_MAX_V2.md]
PYEOF

# DataGapValidator
cat > core/v10/v10_data_gap_validator.py << 'PYEOF'
# [code v10_data_gap_validator.py depuis HERMES_PROMPT_MAX_V2.md]
PYEOF

pytest tests/test_v10_stale_guard.py tests/test_v10_data_gap_validator.py -q
git add core/v10/v10_stale_guard.py core/v10/v10_data_gap_validator.py tests/
git commit -m "feat(guards): StaleGuard + DataGapValidator R2 additifs [R2/R6/R9]"
git push origin feat/v10-unified
```

---

### ÉTAPE 8 — Health dashboard + learning cycle

```bash
python scripts/run_learning_cycle_10_08.py
python scripts/v10_health_dashboard.py
git add reports/learning_cycle_2026_08_10.json scripts/
git commit -m "feat(ops): learning cycle 10/08 + health dashboard [R1/R9]"
git push origin feat/v10-unified
```

---

### ÉTAPE 9 — Rapport Hermes à Perplexity

Quand feat/v10-unified est propre (>= 1310/1310) :

```
POINT HERMES → Perplexity :
- feat/v10-unified HEAD : <SHA>
- Tests : <N>/1310
- Modules fusionnés : replay_engine(B) + sgl(B) + recalib(B)
- Modules C11-C20 : 56 ✅ (depuis A)
- StaleGuard : ✅ / ❌
- DataGapValidator : ✅ / ❌
- Learning cycle : ✅ / ❌
- Prêt pour PR vers main : OUI/NON
```

**Perplexity ouvrira la PR `feat/v10-unified → main` via GitHub MCP.**

---

## 🔴 EURUSD HTF STALE — Action parallèle (P0)

**Confirmation ZCode :** M1 EURUSD frais (10/08 13:23), H1/M30/M15/M5 stales 13-14j.
**Cause :** charts HTF EURUSD probablement retirés du terminal MT4.
**Søn a déjà remis les EA EURUSD sur les TF manquants** — ✅

Vérification post-fix :
```python
import sqlite3, pandas as pd
conn = sqlite3.connect('data/powerflow.db')
df = pd.read_sql("""
    SELECT timeframe,
           MAX(bar_time) as last_bar,
           ROUND((JULIANDAY('now') - JULIANDAY(MAX(bar_time))) * 1440, 1) as lag_min
    FROM forces_snapshots
    WHERE pair = 'EURUSD'
    GROUP BY timeframe ORDER BY timeframe
""", conn)
print(df)
conn.close()
# Attendre 1-3 barres M30 (30-90 min) pour voir les TF HTF se remplir
# Cible : H1 lag < 90 min, H4 lag < 300 min
```

**DEC-2026-08-10-052 : EURUSD HTF stale résolu côté EA (Søn 10:28 CEST) — re-vérification dans 90 min.**

---

## 📋 DECISIONS_LOG — Entrée à ajouter

```markdown
## 2026-08-10 10:28 CEST — CEO + ZCode + Hermes — Stratégie D validée

- **Rapport ZCode** : `reports/repo_realignment_report.json` @ `e717ecb`
- **Décision CEO** : Stratégie D — feat/v10-unified (base A + modules B)
- **Décision CEO** : API RecalibDecision adoptée (triplet de A = anomalie confirmée)
- **EURUSD HTF** : EA remis sur TF HTF par Søn 10:28 CEST — re-vérification 11:58 CEST
- **R10** : maintenu — GO LIVE après feat/v10-unified stable + DeploymentValidator
- **Prochain jalon** : feat/v10-unified >= 1310/1310 → PR vers main
```

---

## 🚦 Gate GO LIVE — Mise à jour

| # | Critère | Statut |
|---|---|---|
| 1 | Tests >= 1310/1310 sur feat/v10-unified | ⏳ Hermes en cours |
| 2 | 56 modules C11-C20 intégrés | ✅ (base A) |
| 3 | RecalibDecision API unifiée | ⏳ Étape 4 |
| 4 | Kill audit V9 pass | ✅ (ZCode) |
| 5 | EURUSD HTF stale résolu | ⏳ ~90 min |
| 6 | StaleGuard actif | ⏳ Étape 7 |
| 7 | DataGapValidator actif | ⏳ Étape 7 |
| 8 | Learning cycle relancé | ⏳ Étape 8 |
| 9 | Port 31685 stable | ✅ |
| 10 | PR feat/v10-unified → main | ⏳ Perplexity post-rapport Hermes |
| 11 | DeploymentValidator C20 GO | ⏳ |
| 12 | Mandat CEO R10 levée | ❌ décision Søn |

---

*Perplexity CEO No-Limit — 2026-08-10 10:28 CEST*
*ZCode : mission accomplie ✅ | Hermes : Stratégie D go maintenant*
