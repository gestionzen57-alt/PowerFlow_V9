# DECISIONS_LOG — PowerFlow V10
**Journal des décisions structurantes**  
**Mis à jour :** 2026-08-14 14:30 CEST

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

---

## 2026-08-14 — Audit VSA institutionnel P1-P5 livré (doctrine Tom Williams)

**Décision :** Livraison 5 patches chirurgicaux sur les modules V10 pour aligner le système sur la doctrine VSA pure (Tom Williams p.47) + Fatman = filtre de contexte uniquement.
- P1 `v10_vsa.py` : ajout `close_location` (0-1) au verdict final. MARKUP exige `close_location >= 0.6` (sinon UPTHRUST = NEUTRAL + flag), MARKDOWN exige `<= 0.4`. `narrow+high_vol` (non-doji) reclassifié en ACCUMULATION/DISTRIBUTION selon `close_location` (avant : fallback direction → faux MARKUP/MARKDOWN). Flag `upthrust` ajouté.
- P2 `v10_filter_compositor.py` : suppression du trigger Fatman (`delta_force >= 0.08` → boost A3→A2) et du boost FC1 (`no_filter_boost` → A3→A2 si aucun filtre actif). Le delta_force est maintenant loggé en `audit["delta_force_context"]` mais n'altère JAMAIS le level. Seul le SMC boost (smc != None) peut promouvoir A3→A2.
- P3 `v10_vsa.py` : ajout σ-bands sur le spread (ATR/20 doctrine). Helper `_pstdev` (stdlib pure), seuils `sigma_narrow=-0.4`, `sigma_wide=0.7`, `sigma_very_wide=1.0`. σ-bands primaire, ratio en fallback si std=0 (R6 backward compat).
- P4 `v10_decision_pipeline.py` : gate triple VSA (doctrine brief #6). `filtered_level A1/A2` exige maintenant AU MOINS 1 confirmation VSA (wyckoff ∈ {MARKUP/MARKDOWN/ACCUMULATION/DISTRIBUTION} OU vsa_multi_tf_ok=True). R6 fail-open : sources absentes (wyckoff_conf=0 ET vsa_multi_tf_ok=None) → on trade sans bloquer. Audit `vsa_confirmations` trace count/sources/sources_present/gate_triple_passed.
- P5 `v10_vsa.py` : gate end-of-bar explicite. `compute_vsa` rejette bougie avec `is_closed_bar=False` (intra-barre interdit). Vérifie fenêtre de calcul entière (min_required bougies).

**Contexte :** Audit institutionnel VSA demandé par CEO suite à divergence entre lecture CEO Søn (Fatman) et code V10 (paradigme CHASSEUR). 6 anomalies suspectées listées dans brief Phase 5 : volume seul (P1), Fatman trigger (P2), calcul intra-barre (P5), open ignoré (couvert par close_location P1), scoring sans σ (P3), absence gate triple (P4).

**Impact :**
- 1422/1422 tests V10 verts cumulés (avant : 1400 + 22 nouveaux tests).
- 4 commits atomiques sur `feat/zcode-night` :
  - `5e78531` P1+P5 v10_vsa.py
  - `6269498` P2 v10_filter_compositor.py
  - `c355f12` P3 σ-bands v10_vsa.py
  - `66771d1` P4 gate triple v10_decision_pipeline.py
- Push remote `9ed0d04..66771d1` réussi (feat/zcode-night).
- Élimination des 6 violations doctrinales identifiées dans brief Phase 5.
- R9 audit : tous les patches ajoutent des champs d'audit (close_location, delta_force_context, vsa_confirmations, gate_triple_passed).

**Auteur :** Hermes (audit CEO Søn, exécution no-limit proactive)
**Statut :** ✅ Actif — branche `feat/zcode-night` HEAD `66771d1`
