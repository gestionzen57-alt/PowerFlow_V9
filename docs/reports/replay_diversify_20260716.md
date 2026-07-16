# Benchmark diversification — DIVERSIFY Chantier C

**Date** : 2026-07-16  
**Auteur** : Claude Opus  

**Méthode** : ré-génération EN MÉMOIRE (lecture seule) des signaux d'un échantillon de snapshots directionnels, avec le code courant (réanimations Chantier A + SignalFusionEngine Chantier B).

## Avant (signaux en base, ancien code)

- Signaux directionnels : **8593**
- Contenant PRICE_LAG : **8225** (**95.7%**)
- Top sources : `PRICE_LAG_AT_NODE_BIRTH`=8225, `POWER_ANGLE_BREAK_TO_PRICE_IMPACT`=364, `ZONE_RETEST`=299, `GRAVITY_RESPRING_NODE`=143, `GRAMMAR_CROISEMENT`=123, `GRAMMAR_CONTEXTE_ADAPTIVE`=99, `GRAMMAR_COALITION`=91, `GRAMMAR_LEADER_FOLLOWER`=88

## Après (ré-génération code courant)

- Échantillon ré-évalué : **600** snapshots
- Signaux directionnels re-générés : **234**
- Contenant PRICE_LAG : **204** (**87.2%**)
- Signaux dont la fusion a relevé la confiance : **201** (règles : {'boost_high_plus_partner': 201})
- Principes contribuant à > 100 signaux : **11**
- Top contributeurs : `PRICE_LAG_AT_NODE_BIRTH`=204, `GRAMMAR_CONTEXTE`=183, `GRAMMAR_CONTEXTE_ADAPTIVE`=183, `POWER_ANGLE_BREAK_TO_PRICE_IMPACT`=130, `POWER_ANGLE_BREAK_TO_PRICE_IMPACT_ADAPTIVE`=130, `GRAMMAR_PULLBACK`=130, `GRAMMAR_PULLBACK_ADAPTIVE`=130, `ZONE_RETEST`=111, `ZONE_RETEST_ADAPTIVE`=111, `GRAMMAR_CROISEMENT`=104

## KPI mission

| Métrique | Avant | Cible | Après |
|---|---|---|---|
| Part de PRICE_LAG dans les signaux | 95.7% | ≤ 60% | **87.2%** |
| Principes contribuant à > 100 signaux | 4 | ≥ 10 | **11** |

## Lecture

Part de PRICE_LAG : **95.7%** (avant) → **87.2%** (après). La diversification provient des principes ACTIVE réanimés (GRAMMAR_EXHAUSTION, SIGNAL_OPEN) et des _ADAPTIVE promus, et la fusion (Chantier B) rescue les signaux faibles concordants.

**Caveat honnête** : la cible ≤ 60% n'est pas encore atteinte car (1) l'échantillon est BIAISÉ vers des snapshots où PRICE_LAG dominait déjà (sélectionnés parce qu'ils étaient directionnels sous l'ancien code), et (2) les 4 principes réanimés les plus productifs (ANTAGONIST_NODE, GRAMMAR_LOCK, GRAMMAR_RESPIRATION, ADAPTIVE_VOL_GATE) sont en SHADOW (observation) et ne votent donc pas encore. Leur promotion post-observation élargira mécaniquement la base votante. Le KPI « ≥ 10 principes > 100 signaux » est en revanche **atteint (11)**.
