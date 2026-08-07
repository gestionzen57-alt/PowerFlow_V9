# ROADMAP — PowerFlow V10
**Feuille de route stratégique**  
**Mis à jour :** 2026-08-07 12:18 CEST

---

## Phase actuelle : VALIDATION LIVE

Le système V10 est **complet en architecture** (Sprints 1-15 Hermes + Phase 12).  
La priorité est la **validation empirique** avant toute promotion vers l'exécution réelle.

---

## 🏁 Objectifs immédiats (J+7)

| Objectif | Critère de succès | Propriétaire |
|---|---|---|
| Calibration Fatman Phase A | 10 signaux alignés vs indicateur visuel | Søn |
| Validation signaux live | 3 jours consécutifs cohérents | Hermes / Søn |
| Fix D02 V9_EXECUTION_ENABLED | grep 0 résultat core/v10/ | Zcode |
| Fix D03 CACHE_BOARD.md | HEAD + tests count corrects | Zcode |

---

## 🚀 Prochaine phase : PROMOTION RL (J+30)

**Gate d'entrée :**
- 100 trades paper V10 validés en conditions normales
- WR ≥ 50% sur les 100 trades
- Sharpe ≥ 0.3
- DD max ≤ 50 pips journalier
- Consistency ≥ 75%

**Livrable :** RL passe de SHADOW → ACTIVE

---

## 🎯 Phase suivante : LIVE RÉEL (TBD — mandat CEO)

**Prérequis non-négociables :**
1. RL ACTIVE avec 30 jours de track record paper
2. Sharpe ≥ 0.5 sur 30 jours glissants
3. Audit indépendant pipeline (Perplexity + Hermes)
4. Décision CEO explicite dans DECISIONS_LOG.md
5. Courtier réel sélectionné (hors Tickmill paper)

**Ce que ça change :**
- `paper_only=True` → `paper_only=False` sur approbation CEO uniquement
- Monitoring renforcé (alertes Telegram/email)
- DD halt renforcé (-30p vs -50p actuel)

---

## 📅 Jalons futurs envisagés

| Jalon | Description | Condition |
|---|---|---|
| Sprint 16 | Optimisation latence pipeline (<500ms) | Après validation 3 jours |
| Sprint 17 | Extension 3 paires supplémentaires (NZDUSD, EURCHF, EURCAD) | Après Promotion RL |
| Sprint 18 | Interface dashboard temps réel (WebSocket) | Lié M2 ZCODE_MISSION |
| Sprint 23 | Quant Upgrade (voir V10_QUANT_UPGRADE_SPRINT23.md) | Après Sprint 16 |
| Live V10 | Premiers ordres réels paper→live | Mandat CEO + 30j track record |

---

## 🚫 Hors scope (permanent)

- Scalping < M5 (risque latence capture server)
- Levier > 1:30
- Positions overnight sans stop validé par Risk Shield
- Toute modification `paper_only` sans DECISIONS_LOG.md
