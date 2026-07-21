# Walk-Forward Validation V9 (Axe 1.3 J3)

> **Statut** : livré 2026-07-21 · kill switch `V9_WALK_FORWARD_ENABLED=0` (OFF, R25' strict)
> **Module** : `core/v9/walk_forward.py` (363 LOC, 4/4 tests verts)
> **CLI** : `scripts/v9_walk_forward.py`
> **Cron** : `V9_WalkForward` quotidien 06:30 UTC (auto, désactivé par kill switch)

---

## 🎯 Problème

Un edge mesuré sur tout l'historique peut être un **artefact d'optimisation** :
le seuil « optimal » a été choisi **après** avoir vu les données.

La validation walk-forward répond à la seule question qui compte pour un stratège
institutionnel :

> **« Un seuil calibré sur le PASSÉ tient-il sur le FUTUR jamais vu ? »**

---

## 🧪 Méthode (anchored walk-forward)

1. **Tri chronologique** des décisions résolues (`is_win IS NOT NULL`,
   `resolution_strategy = 'DYNAMIC'`) par `timestamp ASC`.
2. **Découpe** en `N` fenêtres contiguës (défaut `N=5`).
3. Pour chaque frontière `k` ∈ `1..N-1` :
   - **in-sample** = fenêtres `[0..k-1]` (le passé connu)
   - **out-of-sample** = fenêtre `[k]` (le futur jamais vu)
   - **Calibration in-sample** : grid search sur `CONFIANCE_GRID = [0, 50, 55,
     60, 65, 70, 75, 80, 85, 90]` pour maximiser l'expectancy in-sample
     (plancher `MIN_INSAMPLE_TRADES = 20`).
   - **Application OOS** : applique ce seuil sur la fenêtre OOS, mesure
     expectancy réelle + WR + p-value.
4. **Verdict agrégé** :
   - OOS expectancy moyenne positive ET majoritaire (≥ 50% folds) ET
     significatif (`p < 0.05`) → edge réel.
   - Ratio de dégradation OOS/IS ≥ `DEGRADATION_WARN_RATIO` (0.5) →
     `EDGE_REEL` ; sinon `EDGE_REEL_DEGRADE`.

---

## 📊 Verdict taxonomy

| Verdict | Condition |
|---|---|
| **EDGE_REEL** ✅ | OOS pos + majoritaire + significatif + dégradation faible |
| **EDGE_REEL_DEGRADE** 🟡 | OOS pos + significatif mais ratio < 0.5 (edge réel sur-estimé) |
| **OVERFITTING** 🔴 | OOS expectancy moyenne négative |
| **NON_CONCLUANT** ⚪ | OOS positif mais non significatif ou minoritaire |
| **DONNEES_INSUFFISANTES** ⚫ | Moins de trades que le plancher |

---

## ⚠️ Provenance des données (caveat empirique)

Cette validation lit `decisions.resolution_pips` / `decisions.is_win`, produits
par le **résolveur offline**. Ce résolveur **n'est pas path-dependent** (il ne
rejoue pas TP/SL barre par barre comme `ExitSimulator` en clôture live).

**Un WR out-of-sample de 95-99 % est le symptôme de cet artefact de résolution**
(biais de distribution documenté), **PAS d'un edge réellement exploitable à ce
niveau**.

À lire donc en **valeur relative** :
- La **stabilité** du seuil calibré (in-sample vs out-of-sample)
- La **dégradation entre folds**
- Le **rapport OOS/IS expectancy** (ratio)

… restent des signaux valides. Le **niveau absolu** de WR/expectancy est gonflé
par la résolution offline et ne doit pas être pris au pied de la lettre.

**La vérité live vient de** `close_open_trades()` + `ExitSimulator`
(≈ breakeven après coûts, audit Opus 17/07 §fiabilité sim).

---

## 🧮 Métriques cibles (motion CEO future)

| KPI | Cible | Source |
|---|---|---|
| OOS expectancy moyenne | > 0 pips | `walk_forward.mean_oos_expectancy` |
| Ratio dégradation OOS/IS | ≥ 0.5 (cible 1.0) | `walk_forward.degradation_ratio` |
| Folds OOS positifs | ≥ 50% (cible 100%) | `walk_forward.oos_positive_folds` |
| p-value OOS agrégée | < 0.05 | `walk_forward.pooled_oos_p_value` |
| Verdict | EDGE_REEL ✅ | `walk_forward.verdict` |

**Verdict NO-GO motion** : si verdict `OVERFITTING` ou `DONNEES_INSUFFISANTES`
3 jours de suite → escalade CEO.

---

## 🛡️ Garde-fous (R6 défensif)

- **Lecture seule DB** : `mode=ro`, aucun write, aucune migration.
- **Try/except** sur chaque fold : un fold en échec n'arrête pas les autres.
- **Plancher trades** : `MIN_INSAMPLE_TRADES = 20`, `MIN_OOS_TRADES = 10`.
- **Verdict par défaut** : `DONNEES_INSUFFISANTES` si la DB n'a pas assez
  d'historique.

---

## 🚦 Intégration pipeline

```
V9_WalkForward cron (06:30 UTC, kill switch OFF par défaut)
  ↓
scripts/v9_walk_forward.py --windows 5
  ↓
WalkForwardValidator.run()
  ↓
docs/reports/walk_forward_<date>.md  (rapport Markdown)
  ↓
Résultat : verdict EDGE_REEL / OVERFITTING / etc.
```

**Aucune activation live** (R25' strict) : le module tourne en mode diagnostic,
sans modifier la calibration live. Activation = motion CEO explicite.

---

## 📚 Références

- `core/v9/walk_forward.py` — module principal (363 LOC)
- `tests/test_v9_walk_forward.py` — tests (4 verts)
- `scripts/v9_walk_forward.py` — CLI smoke
- `scripts/_run_v9_walk_forward.bat` — wrapper cron
- `scripts/install_v9_walk_forward_cron.bat` — installateur idempotent
- `docs/reports/walk_forward_20260721.md` — dernier rapport live (verdict
  `EDGE_REEL`, OOS expectancy +6.741 pips, ratio 1.06, 4/4 folds positifs)
- `core/v9/kill_switches.py::walk_forward_enabled` — kill switch
- `config/v9_kill_switches.env` : `V9_WALK_FORWARD_ENABLED=0`
- DECISIONS_LOG.md §2026-07-21 Axe 1.3 J3

---

## 🔗 Cohérence Roadmap V2

- **J1** ✅ Bayesian Calibrator (commit `bead380`)
- **J2** ✅ Kelly câblé (commit `d93b845`)
- **J3** ✅ Walk-forward OOS (Axe 1.3 J3, ce document)
- **J4** ⏳ Brier + Platt scaling (déjà partiellement livré dans Bayesian)
