---
name: powerflow-v9-risk-attribution
description: Use when computing risk attribution by principle × regime × session (Phase 132).
trigger: "Phase 132 risk attribution, principle regime session cross, concentration risque"
category: powerflow-v9
---

# PowerFlow V9 — Risk Attribution (Phase 132)

Module additif qui décompose le risque par croisement `(principe_set, regime, session)`.
Permet d'identifier les concentrations de risque et calibrer des kill switches ciblés.

## Kill switch

- Pas de kill switch (lecture seule DB).

## Module

`core/v9/v9_risk_attribution.py` (NEW Phase 132).

API :
- `compute_risk_attribution(trades=None, db_path=DB_PATH) -> dict`
- `top_risk_concentrations(attribution, top_n=5) -> list[dict]`
- `render_report(attribution, top_risks) -> str`
- `main(db_path, output, report) -> int`

## Métriques

- `total_n` : nombre de trades analysés
- `total_pnl` : PNL cumulé
- `concentration` : % du PNL négatif concentré sur top-5 croisements
- `by_cross` : stats par croisement (principes|regime|session)
- `by_principe` / `by_regime` / `by_session` : agrégations 1D

## Résultats live (2026-08-03 06:30 UTC, n=2101 trades)

- **Concentration** : 12.3% (top 5 croisements = -2500p sur -5363p négatif)
- **Top risque** : combinaisons GRAMMAR_* (GRAMMAR_CONTEXTE × GRAMMAR_EXHAUSTION etc.)
- **Insight** : justifiait blacklist ciblée croisement (L17 Phase 134)

## Tests

`tests/test_v9_risk_attribution.py` : 7/7 verts (trades vides,
aggregation simple, concentration top5, ordre top_risk, exclusion PNL
positif, render report, main DB synthétique).

## Doctrine

- R2 additif (NEW module, 0 modif core/ partagé)
- R6 fail-open (trades=None → all empty)
- R7 tests verts (7/7 ajoutés)
- R14 git vérité (chiffres du SQL réel)
- R22 sous-unité unique
- R28 Hermes git unique