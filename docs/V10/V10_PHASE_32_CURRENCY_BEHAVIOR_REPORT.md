# V10 — Phase 32 : Currency Behavior — Rapport de lecture comportementale

**Date** : 2026-08-05 · **Auteur** : ZCode (mandat CEO Søn, plein pouvoir)
**HEAD** : `6255d55` + Phase 32 (à committer)
**Tests** : 43 nouveaux verts (39 → 43 avec fidélité extrême) — cumul **774/774** zéro régression

---

## 1. Mission CEO reformulée

> « V10 doit refléter la réalité du marché et pouvoir comprendre le
> comportement des forces de devises. »

Livrable : `core/v10/v10_currency_behavior.py` — 5 couches qui transforment
8 séries de scores bruts en compréhension, avec un **garde-fou de fidélité**
(est-ce que les forces reflètent les prix ?) et une **réversibilité totale**
(jamais bloqué par un choix).

---

## 2. Architecture livrée (5 couches)

| Couche | Fonction | Contenu |
|---|---|---|
| 0 — Observation | `load_currency_series` | 8 forces + prix depuis `forces_snapshots`, filtre saturation, alignement strict, R6 fail-open |
| 1 — Comportement | `classify_currency_states`, `detect_coalitions`, `compute_leadership`, `classify_regime`, `compute_lead_lag` | états (RALLYE/DECLINE/ROTATION/RETOURNEMENT/RANGE), coalitions glissantes, leader/follower + rotation, régimes double lecture, causalité H4→M30 |
| 2 — Fidélité | `compute_fidelity`, `compute_fidelity_extreme`, `compute_fidelity_composite` | corr forces→rendements futurs + **WR directionnel aux queues P90/P10** (découverte clé) + composite M30/H1 pondéré |
| 3 — Apprentissage | `calibrate_regime_thresholds`, `detect_drift`, `apply_behavior_config`/`reset_behavior_config` | calibration R8 (percentiles réels), drift ADWIN simplifié, **réversibilité à chaud** (registre des choix) |
| 4 — Expression | `build_narrative`, `build_causal_narrative`, `build_behavior_context` | narrative V1 (1 phrase CEO) + V2 (récit causal) + `behavior_context` complet |

---

## 3. 🔍 DÉCOUVERTES SUR DONNÉES RÉELLES (R9 honnête)

### 3.1 La corrélation linéaire forces→prix est ≈ 0
Sur 3 paires (GBPUSD, USDJPY, AUDUSD), composite linéaire : **-0.012 à +0.065**.
Toutes les corr par devise ∈ [-0.11, +0.14]. → Les forces V9 n'ont **pas**
de pouvoir prédictif linéaire sur les rendements M30/H1.

### 3.2 MAIS le signal vit aux extrêmes (P90/P10) ⭐
Quand une force est au percentile extrême, le rendement futur devient
**directionnel** :

| Paire | Force extrême | WR directionnel | n échantillons |
|---|---|---|---|
| GBPUSD | AUD (P10 faible) | **86.4%** | 22 |
| GBPUSD | JPY (P90 fort) | 73.9% | 23 |
| AUDUSD | CAD (P90 fort) | **90.0%** | 20 |
| AUDUSD | USD (P90 fort) | 75.0% | 20 |
| AUDUSD | JPY (P10 faible) | 80.0% | 20 |
| USDJPY | CHF (P90 fort) | 65.2% | 23 |

→ **Verdict** : GBPUSD et AUDUSD **RELIABLE** via lecture extrême ;
USDJPY **DÉGRADÉE** (1 seule devise fiable — exclue du gate R10).

### 3.3 Régime SAFE_HAVEN partout (calibré)
Les 3 paires lisent **SAFE_HAVEN** — mais par la **lecture recalibrée**
(seuils proposés : risk_on **59.9** / safe_haven **38.6** vs hérité 65.0),
pas par la lecture héritée. → La calibration R8 change réellement le
verdict de régime.

### 3.4 Causalité FAST_LEADS
M30 précède H4 (2-3/8 devises mènent sur le court TF) — cohérent avec
le tempo scalp/paper micro-lot actuel.

### 3.5 Rotation de leadership détectée
GBPUSD : rotation USD→CAD (CAD mène à 58.7) — la lecture change en
continu, pas figée.

---

## 4. Réversibilité (règle d'or CEO)

- `apply_behavior_config({...})` : surcharge toute constante à chaud
  (merge profond, idempotent, audit JSON)
- `reset_behavior_config()` : restaure les defaults
- `get_behavior_state()` : registre des choix (config active + defaults
  + n_applies + dernier audit) — **jamais bloqué par un choix**

---

## 5. Doctrine V10

| Règle | Statut |
|---|---|
| R1 AGIR | ✅ autopilote, mandat CEO plein pouvoir |
| R2 additif pur | ✅ 0 import core/v9/ (vérifié) |
| R3 INVENTER | ✅ fidélité extrême découverte sur données réelles, pas théorique |
| R5 CoT | ✅ narrative V1 + causale V2 |
| R6 fail-open | ✅ 4 cas (DB absente, table absente, données courtes, timestamps invalides) |
| R7 tests verts | ✅ 774/774 cumulés |
| R8 auto-calibration | ✅ seuils régime calibrés (59.9/38.6) + apply à chaud |
| R9 audit honnête | ✅ corr linéaire ≈ 0 documentée (pas de survente) |
| R10 capital protégé | ✅ USDJPY DÉGRADÉE exclue du gate ; kill switch fidélité |

---

## 6. Fichiers livrés

- `core/v10/v10_currency_behavior.py` (~750 lignes, stdlib only)
- `tests/test_v10_currency_behavior.py` (43 tests)
- `scripts/v10_currency_behavior_demo.py` (CLI + rapport JSON)
- `reports/v10_currency_behavior_20260805.json` (audit complet)

## 7. Prochaines étapes suggérées (à valider CEO)

1. **Étape 2** : table de stats comportementales par (devise, TF, session,
   état) → apprentissage R4 + backtest des régimes
2. **Étape 3** : branchement `behavior_context` dans le signal orchestrator
   (A1/A2/A3) — gate : seulement si `extreme_reliable` ET `reliable`
3. **Watchdog** : détection de rotation de régime en live (alerte quand
   SAFE_HAVEN→RISK_ON ou vice-versa)
4. **Reconstruire les forces en natif V10** (TA lecture) — la corr linéaire
   ≈ 0 suggère que les forces V9 bruitées peuvent être remplacées par des
   forces calculées sur OHLC+volume+spread (cohérent audit Phase 180)
