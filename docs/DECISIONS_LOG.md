# DECISIONS_LOG — PowerFlow V10
**Journal des décisions structurantes**  
**Mis à jour :** 2026-08-07 12:18 CEST

> Format : DATE · DÉCISION · CONTEXTE · IMPACT · AUTEUR

---

## Format standard

```
## YYYY-MM-DD — [TITRE COURT]
**Décision :** [Ce qui a été décidé]
**Contexte :** [Pourquoi cette décision était nécessaire]
**Impact :** [Ce que ça change concrètement]
**Auteur :** [CEO / Zcode / Hermes / Perplexity]
**Statut :** [Actif / Révoqué / Remplacé par DXX]
```

---

## 2026-08-05 — Réparation Safe Haven
**Décision :** Fix `v10_currency_strength._compute_raw_returns` — inversion signe paires inversées  
**Contexte :** USDJPY/USDCHF/USDCAD classaient JPY/CHF comme faibles quand ils s'appréciaient  
**Impact :** Safe Haven (Principe 3 Fatboy) et rankings devises corrects. 96 tests verts.  
**Auteur :** Zcode (audit R9)  
**Statut :** ✅ Actif — commit `885a851`

## 2026-08-05 — Doctrine paper-only V10 confirmée
**Décision :** `paper_only=True` hard-codé dans tous les composants V10. `V9_EXECUTION_ENABLED=1` est un résidu V9, pas un enabler V10.  
**Contexte :** Audit R9 exhaustif — 0 occurrence `order_send` dans `core/v10/`  
**Impact :** Zéro risque d'ordre réel accidentel. Tous les signaux sont paper-only.  
**Auteur :** CEO (Søn) + audit Hermes R9  
**Statut :** ✅ Actif — doctrine permanente

## 2026-08-04 — Strategy Layers devient wrapper
**Décision :** `v10_strategy_layers` réécrit en wrapper de `v10_filter_compositor` — un seul cœur de filtrage  
**Contexte :** Doublon détecté lors de Sprint 4 Hermes — deux implémentations ICT+SMC parallèles  
**Impact :** Zéro duplication, maintenance centralisée sur compositor  
**Auteur :** Zcode (Sprint reconciliation)  
**Statut :** ✅ Actif

## 2026-08-03 — Stack quant libérée (doctrine CEO no-limit)
**Décision :** Activation scipy/statsmodels/sklearn/hmmlearn/ruptures/arch/plotly/finta — tous dans `pyproject.toml` v0.10.0  
**Contexte :** Blocage artificiel sur les librairies quant imposait des contournements fragiles  
**Impact :** HMM, GARCH, ruptures détection de régime — tous opérationnels en test et production  
**Auteur :** CEO (Søn)  
**Statut :** ✅ Actif

## 2026-07-21 — Verdict HOLD auto-recalibrateur
**Décision :** Auto-recalibrateur Sprint 7 maintient REVERT conservateur car after_wr=0 < before_wr=0.49  
**Contexte :** Tentative promotion paramètres avec données insuffisantes sur 3 jours  
**Impact :** Paramètres V10 figés jusqu'à 100 trades paper validés  
**Auteur :** Hermes Sprint 7  
**Statut :** ✅ Actif — réévaluation à 100 trades

## 2026-07-18 — Architecture Cognitive Continuum
**Décision :** Pont mémoire V9 read-only + registre v10_behaviors + Cortex RAG sur mémoire propre  
**Contexte :** V10 devait capitaliser sur l'apprentissage V9 sans polluer le cœur  
**Impact :** 17 modules de lecture connectés, 0 orphelin. Auto-cohérence documentée.  
**Auteur :** Hermes (Sprints Cognitive)  
**Statut :** ✅ Actif

## 2026-06-01 — Promotion Shadow requiert 100 trades
**Décision :** RL ne peut passer SHADOW→ACTIVE qu'après 100 trades paper avec Sharpe≥0.5 (gates R10 : WR≥50/Sharpe≥0.3/DD≤50p/consistency≥75%)  
**Contexte :** Risque de surapprentissage sur données insuffisantes  
**Impact :** Promotion bloquée actuellement — 0 trades paper V10 validés en conditions normales  
**Auteur :** CEO (Søn)  
**Statut :** ✅ Actif

---

## Template nouvelle décision

```markdown
## YYYY-MM-DD — [TITRE]
**Décision :**
**Contexte :**
**Impact :**
**Auteur :**
**Statut :** En cours
```
