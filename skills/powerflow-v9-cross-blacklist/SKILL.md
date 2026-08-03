---
name: powerflow-v9-cross-blacklist
description: Use when analyzing or activating cross blacklists (Phase 134 L17 GRAMMAR*REJET*asie).
trigger: "Phase 134 L17, cross blacklist, GRAMMAR REJET asie, concentration risque"
category: powerflow-v9
---

# PowerFlow V9 — L17 Cross Blacklist (Phase 134)

Blacklist statique des croisements `(principe_set, regime, session)` identifiés
comme concentrateurs de risque négatif par la Risk Attribution Phase 132.

## Kill switch

- `V9_HEATMAP_L17_CROSS_BLACKLIST_ENABLED=1` (motion CEO 03/08 active)

## Module

`core/v9/v9_cross_blacklist.py` (NEW Phase 134).

API :
- `cross_blacklist_enabled() -> bool`
- `get_static_blacklist() -> list[tuple]`
- `is_cross_blacklisted(principes, regime, session) -> bool`
- `evaluate_cross_blacklist(principes, regime, session) -> dict`

## Blacklist statique (motion CEO 03/08)

5 croisements `(GRAMMAR_*, REJET, asie)` :

| Principes | Regime | Session |
|---|---|---|
| GRAMMAR_CONTEXTE × GRAMMAR_CONTEXTE_ADAPTIVE × GRAMMAR_EXHAUSTION | REJET | asie |
| GRAMMAR_CONTEXTE_ADAPTIVE × GRAMMAR_EXHAUSTION × GRAMMAR_PULLBACK | REJET | asie |
| GRAMMAR_ABSORPTION_ADAPTIVE × GRAMMAR_CONTEXTE × GRAMMAR_CONTEXTE_ADAPTIVE | REJET | asie |
| GRAMMAR_EXHAUSTION × GRAMMAR_PULLBACK × GRAMMAR_PULLBACK_ADAPTIVE | REJET | asie |
| GRAMMAR_CONTEXTE_ADAPTIVE × GRAMMAR_PULLBACK × GRAMMAR_PULLBACK_ADAPTIVE | REJET | asie |

## Audit SQL live (Phase 132, n=2101 trades)

- **Concentration** : 12.3% du PNL négatif sur top-5 croisements
- **Top 5 PNL** : -217p / -197p / -180p / -170p / -158p
- **WR top 5** : 0% sur 14-28 trades par croisement
- **Insight** : neutralise ~2500 pips de perte cumulée sans toucher aux principes GRAMMAR

## Normalisation

- Principes : `tuple(sorted(strip(p)))` pour stabilité d'ordre
- Regime : UPPERCASE
- Session : lowercase

## Tests

`tests/test_v9_cross_blacklist.py` : 15/15 verts (version, static 5 entrées,
normalisation sorted/strip/empty, kill switch OFF/ON, match exact,
no-match regime, no-match session, order-independent, case-insensitive,
empty principes, immutable default).

## Doctrine

- R2 additif (NEW module, 0 modif core/ partagé)
- R6 fail-open (kill switch OFF, principes vide, hors liste → pass-through)
- R7 tests verts (15/15 ajoutés)
- R14 git vérité (audit SQL Phase 132)
- R22 sous-unité unique
- R25' motion CEO explicite
- R28 Hermes git unique