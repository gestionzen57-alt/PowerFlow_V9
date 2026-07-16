# Rapport DIVERSIFY — Réanimation des 6 principes morts

**Date** : 2026-07-16
**Auteur** : Claude Opus (mandat « Donne 10 yeux au système »)
**Périmètre** : Chantier A — réanimation des principes à 0 % hit rate
**Rollout** : Mix (décision CEO Søn) — 2 ACTIVE, 4 SHADOW en observation 24-48h

---

## 1. Contexte

PRICE_LAG représentait 93 % des signaux (edge decay -18.9 %). Six principes
étaient à **exactement 0 % de déclenchement** malgré des milliers d'évaluations.
Diagnostic mené sur **données réelles** (`data/v9_forces.db`, 3200+ contextes
par-devise reconstruits via `_load_shared_context` + `_build_currency_context`).

## 2. Diagnostic — cause racine vérifiée (≠ hypothèses initiales)

| Principe | Cause supposée (mandat) | Cause RÉELLE vérifiée |
|---|---|---|
| GRAMMAR_EXHAUSTION | `z_current` jamais ≥ 2.0 | z_current atteint ≥2 (8412×), mais **state alors toujours RUPTURE** (207/207) ; le filtre `[EARLY_EXTREME, EXTENSION]` exclut tout. `EXTENSION` n'existe même pas comme valeur. |
| SIGNAL_OPEN | `window_statut` jamais ouverte | `window_statut` n'est **jamais "exploitable"** (valeurs réelles : absente/ouverte/invalidee/ambigue/fragile). Confusion de vocabulaire avec `exploitability.statut`. |
| GRAMMAR_RESPIRATION | `zone_type` jamais respiration | `_detect_zone_type` testait `"COMPRESSING"` (majuscule V8) alors que la vraie valeur DB est `"compression"` (minuscule → `.upper()` = `"COMPRESSION"`). `"COMPRESSING" ∉ "COMPRESSION"` → respiration jamais détectée (0/3200). En plus `compression_extension_etat` n'était propagé que sur H1/M5. |
| GRAMMAR_LOCK | compression jamais détectée | Dépend de `zone_type == respiration` → même cause que ci-dessus. |
| ANTAGONIST_NODE | `h1_state` jamais ≠ NEUTRAL | **Faux** : h1/m5 sont toujours HAUSSIERE tous les deux (dérivés de la devise GLOBALEMENT la plus forte, identique cross-TF). Vrai bloqueur : `h1_dir != m5_dir` jamais vrai. La dérivation globale est incorrecte pour un node_rule évalué **par-devise**. |
| ADAPTIVE_VOL_GATE | `coalition_strength` jamais ≥ seuil | **Mismatch d'échelle** : `coalition_strength` est un ratio 0-1 (max 0.87), comparé à `adaptive_coalition_threshold ≈ 6.99` (échelle brute V8, baseline 5.38). |

## 3. Correctifs

- **YAML (2)** — EXHAUSTION : `state ∈ {EARLY_EXTREME, RUPTURE}`. SIGNAL_OPEN : `window_statut == ouverte`.
- **Moteur `_detect_zone_type`** — vocabulaire `"COMPRESS"` (couvre `compression` DB et `COMPRESSING` legacy, exclut extension/neutre).
- **Moteur `_load_shared_context`** — propagation de `compression_extension_etat` sur **tous** les timeframes.
- **Moteur `_build_currency_context`** — dérivation h1/m5 dir/state **par-devise** (override), sémantique correcte d'un node_rule par-devise.
- **Moteur seuil normalisé** — `adaptive_coalition_threshold_norm = 0.60 × mult` (échelle 0-1, calibré empiriquement) ; ADAPTIVE_VOL_GATE le consomme.

## 4. Résultats — taux de déclenchement (ré-évaluation en mémoire, 2000 snapshots réels)

| Principe | Avant | Après | Statut rollout | Zone saine (1-5%) |
|---|---|---|---|---|
| GRAMMAR_EXHAUSTION | 0.00 % | **5.04 %** | ACTIVE | ✓ (haut) |
| SIGNAL_OPEN | 0.00 % | **1.70 %** | ACTIVE | ✓ |
| GRAMMAR_LOCK | 0.00 % | **1.24 %** | SHADOW | ✓ |
| GRAMMAR_RESPIRATION | 0.00 % | **1.24 %** | SHADOW | ✓ |
| ADAPTIVE_VOL_GATE | 0.00 % | **3.70 %** | SHADOW | ✓ |
| ANTAGONIST_NODE | 0.00 % | **19.23 %** | SHADOW | ✗ (à resserrer selon WR observé) |

**Calibration ADAPTIVE_VOL_GATE** (baseline normalisée) : 0.40 → 34.6 % (bruité) ;
**0.60 → 3.70 % (retenu)** ; 0.70 → 0 %.

## 5. Rollout Mix (décision CEO Søn)

- **ACTIVE** (fix YAML trivial, risque quasi nul) : GRAMMAR_EXHAUSTION, SIGNAL_OPEN.
- **SHADOW** (fix moteur, observation 24-48h avant re-promotion R25') : GRAMMAR_LOCK, GRAMMAR_RESPIRATION, ANTAGONIST_NODE, ADAPTIVE_VOL_GATE.

Les SHADOW déclenchent et sont journalisés (calibration) mais **ne votent pas**
dans le SignalGenerator. Promotion conditionnée à un WR/taux sain observé.

## 6. KPI mission

| Métrique | Avant | Cible | Après |
|---|---|---|---|
| Principes à 0 % hit rate | 6 | ≤ 2 | **0** ✓ |
| Diversification (principes productifs) | — | — | +6 lecteurs |

## 7. Garde-fous respectés

- **R2 additif** : PRICE_LAG intact (aucune modification de son YAML/chemin).
- **R6** : lectures défensives try/except sur tous les champs dérivés.
- **R18** : zéro LLM dans le cœur cognitif (code pur).
- **R7** : suite complète verte (voir commit). Tests encodant des bugs corrigés + justifiés.
- **order_executor.py / config.py trading** : non touchés (Phase 12 gelée). config.py modifié uniquement sur PRINCIPLE_ACTIVE_IDS (rollout).

## 8. Suite (hors scope session)

- Chantier B — SignalFusionEngine (agréger principes faibles).
- Chantier C — benchmark replay complet WR/expectancy avant/après.
- Observation 24-48h des 4 SHADOW → décision de re-promotion ACTIVE (dont resserrage éventuel d'ANTAGONIST_NODE).
