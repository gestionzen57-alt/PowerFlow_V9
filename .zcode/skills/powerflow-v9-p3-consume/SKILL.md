---
name: powerflow-v9-p3-consume
description: "P3-CONSUME — créer un principe YAML qui CONSOMME les seuils adaptatifs (adaptive_coalition_threshold, adaptive_antagonism_threshold, adaptive_pliure_threshold) posés dans _load_shared_context par P3-WIRE. Premier principe consommateur : ADAPTIVE_VOL_GATE (SHADOW)."
category: trading
tags: [v9, p3-consume, adaptive-thresholds, value-field, principle-yaml, shadow]
statut: actif
derniere_maj: 2026-07-14
version: 0.1.0
note_chantier: aligne au HEAD 5e1b9df (1277 verts + 2 skipped + 0 fail)
---

# PowerFlow V9 — P3-CONSUME (Adaptive Thresholds Consumer)

## Purpose

`core/v9/adaptive_thresholds_at_runtime.py` (commit `5abfa2b`) expose
`get_effective_thresholds()` qui retourne un dict scalé par le
multiplicateur composite (vol * news * tf, borné [0.5, 2.0]).

`core/v9/principle_engine._load_shared_context` (commit `1babf14`,
P3-WIRE) pose les 3 clés dans le context partagé :
- `adaptive_coalition_threshold`
- `adaptive_antagonism_threshold`
- `adaptive_pliure_threshold`

P3-CONSUME (commit `5e1b9df`) livre le **premier principe** qui
CONSOMME ces seuils via le pattern `value_field` (déjà supporté par
`evaluate_condition`, utilisé par `ANTAGONIST_NODE.yaml` et
`ZONE_RETEST.yaml`).

## Le pattern value_field

```yaml
- field: coalition_strength
  op: '>='
  value_field: adaptive_coalition_threshold
```

`value_field` est résolu dans `_resolve_condition_target` :
```python
def _resolve_condition_target(cond, context):
    if "value_field" in cond:
        return context.get(cond["value_field"])
    return cond.get("value")
```

Donc `value` (constante) OU `value_field` (autre champ du context).
Les deux clés sont mutuellement exclusives.

## Pourquoi pas modifier evaluate_condition

Aucun besoin : `value_field` est déjà supporté. On consomme les
champs adaptatifs en YAML uniquement. Pas de modif moteur, pas de
risque R8 (aucun core/v9/* existant modifié).

## Le principe ADAPTIVE_VOL_GATE (commit 5e1b9df)

Premier consommateur des seuils adaptatifs. SHADOW par défaut (R25').
Kind: `node_rule`. Scope: M5/M15/H1/H4 (aligné sur les 9 node_rule
historiques, jamais M30, règle 29).

```yaml
conditions:
  # Filtre contexte : on ne consomme les seuils adaptatifs que si
  # on est en vol élevée (HIGH/EXTREME). En LOW/NORMAL, le seuil
  # baseline est OK, pas besoin d'adaptation.
- field: vol_regime
  op: in
  value: [HIGH, EXTREME]
  # Dégradation gracieuse R6 (R25' "ne lève jamais") : si les seuils
  # adaptatifs ne sont pas dans le context (P3-WIRE OFF), le principe
  # ne déclenche pas. On gate sur leur présence AVANT les comparaisons
  # value_field (qui tapent dans None sinon et font crasher
  # evaluate_condition sur TypeError float >= None).
- field: adaptive_coalition_threshold
  op: is_not_null
  value: true
- field: adaptive_antagonism_threshold
  op: is_not_null
  value: true
  # Consommation réelle des seuils adaptatifs (P3-CONSUME) :
  # coalition_strength >= adaptive_coalition_threshold
  # (en HIGH baseline 5.38, en EXTREME * 1.5 = 8.07, etc.)
- field: coalition_strength
  op: '>='
  value_field: adaptive_coalition_threshold
  # antagonism_strength <= adaptive_antagonism_threshold
- field: antagonism_strength
  op: '<='
  value_field: adaptive_antagonism_threshold
  # Gate session : on n'evalue pas en transition weekend (regle 29).
- field: session_marche
  op: is_not_null
  value: true
```

## Comportement runtime par état du switch P3-WIRE

| V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED | adaptive_*_threshold dans context | ADAPTIVE_VOL_GATE triggered? |
|---|---|---|
| 0 (OFF) | absent (None) | Non — gates is_not_null retombent à False |
| 1 (ON) + vol LOW/NORMAL | présent | Non — filtre vol_regime |
| 1 (ON) + vol HIGH/EXTREME + coalition >= adaptive | présent | Oui |
| 1 (ON) + vol HIGH/EXTREME + coalition < adaptive | présent | Non |

## Tests pytest

10 tests dans `tests/test_p3_consume.py` :
- Catalogue (presence, count 27, kind/status, value_field uses)
- Cas passants (HIGH, EXTREME, seuils satisfaits)
- Cas non passants (NORMAL, seuils absents, coalition/antagonism hors seuil)
- Sanity check `evaluate_condition` value_field numérique (documente le
  TypeError sur target=None, protégé par is_not_null en amont dans le YAML)

5 tests existants adaptés (compte 26 → 27) :
- test_principle_engine.py : 4 tests (loads, kind, v9_status, principles_dir)
- test_engine_syncs_principles_table : count 26 → 27
- test_p3_wire_integration.py : non-régression limitée aux 26 principes
  historiques, ADAPTIVE_VOL_GATE exclu par design
- test_all_27_yaml_evaluate_with_full_context.py : count 26 → 27
- test_archived_yamls_not_in_active_ids.py : shrinks_from_27_to_26 → 28_to_27
- test_yaml_loads_25_unique_ids.py : 26 → 27 unique IDs

## Recipe — ajouter un nouveau principe P3-CONSUME

1. Identifier le(s) seuil(s) adaptatif(s) à consommer :
   `adaptive_coalition_threshold` / `adaptive_antagonism_threshold` /
   `adaptive_pliure_threshold`.

2. Écrire le YAML dans `core/v9/principles/NEW_PRINCIPLE.yaml` avec :
   - `kind: node_rule` ou `kind: grammar`
   - `v9_status: SHADOW` (R25' : pas de promotion ACTIVE sans motion
     CEO explicite)
   - `scope.timeframes` aligné sur les node_rule historiques
     (M5/M15/H1/H4, jamais M30)
   - Première condition : `is_not_null` sur chaque seuil adaptatif
     (gate anti-TypeError)
   - Conditions suivantes : `value_field: adaptive_*_threshold` sur
     les comparaisons numériques

3. Ajouter au moins 5 tests dans `tests/test_p3_consume.py` (ou créer
   `tests/test_<nom>.py` si nouveau chantier) couvrant :
   - Cas passant (vol haute + seuils satisfaits)
   - Cas non passant (vol basse / seuils absents / valeurs hors seuil)

4. Adapter les tests count-globaux qui asserent == 27 (passer à 28).

5. Backup R8 (nouveau fichier YAML : pas de backup MD5 requis,
   convention Brief Q1 trader_mini_baseline).

6. Commit atomique R22 (1 commit par unité logique).

7. Push R28 (motion CEO explicite ou délégation implicite par défaut).

## Pré-requis P3-WIRE actif

Sans `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=1`, les 3 clés
`adaptive_*_threshold` ne sont pas posées dans le context → le
principe ADAPTIVE_VOL_GATE ne déclenche jamais (gates is_not_null).
C'est la dégradation gracieuse R6/R25' : zéro impact si P3-WIRE OFF,
consommation effective dès que P3-WIRE est ON.

## Fissures connues

- `evaluate_condition` lève `TypeError` quand `target=None` (cas où
  `value_field` pointe vers un champ absent du context). Le pattern
  propre = gate `is_not_null` en amont dans le YAML, pas dans le
  moteur. Voir commit `5e1b9df` et `tests/test_p3_consume.py` pour
  l'exemple.
- Le moteur `evaluate_condition` n'a pas été modifié (R8 strict :
  aucun core/v9/* existant touché).

## Files

- `core/v9/principles/ADAPTIVE_VOL_GATE.yaml` — premier principe
  consommateur (SHADOW)
- `core/v9/adaptive_thresholds_at_runtime.py` — module pur P3
- `core/v9/principle_engine.py` — `_load_shared_context` pose les
  3 clés (commit `1babf14` P3-WIRE), `evaluate_condition` supporte
  `value_field` (pattern existant)
- `tests/test_p3_consume.py` — 10 tests verts

## Doctrine

- R6 ✓ pas de simulation, dégradation gracieuse via is_not_null
- R7 ✓ aucune régression (1277 → 1277 verts, 0 fail)
- R8 ✓ nouveau fichier YAML, pas de modif core/v9/* existant
- R18 ✓ pas de LLM dans la boucle
- R22 ✓ 1 commit par unité logique (commit `5e1b9df`)
- R25' ✓ ADAPTIVE_VOL_GATE SHADOW par défaut, promotion ACTIVE = motion
  CEO explicite (R25' assoupli 2026-07-14, DOCTRINE.md)
- R26 ✓ 10 tests pytest + 5 tests existants adaptés
- R28 ✓ push direct (motion CEO « go la suite » = R28 assoupli)

## Référence

- DECISIONS_LOG §2026-07-14 « P3-CONSUME livré (premier principe
  consommateur de seuils adaptatifs) »
- DOCTRINE.md §R25' (assoupli 2026-07-14)
- workspace/perplexity/COORDINATION_NOTE.md (assignation P3-CONSUME
  à Hermes par ZCode)
- commit `5abfa2b` (P3 module pur)
- commit `1babf14` (P3-WIRE, pose les seuils dans le context)
- commit `5e1b9df` (P3-CONSUME, premier consommateur)
