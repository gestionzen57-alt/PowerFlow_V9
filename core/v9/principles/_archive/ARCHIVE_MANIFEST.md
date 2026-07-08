# ARCHIVE_MANIFEST — core/v9/principles/_archive/

## Statut
Registre des principes YAML retirés du catalogue actif (`core/v9/principle_engine.py`
charge `core/v9/principles/*.yaml` via `Path.glob("*.yaml")`, non récursif — un fichier
placé dans ce sous-dossier n'est plus jamais chargé ni évalué).

## Règle d'archivage
Classification A/B/C/D de [`docs/doctrine/MIGRATION_POLICY_V9.md`](../../../docs/doctrine/MIGRATION_POLICY_V9.md).
Un principe est archivé ici (classe **C**) quand sa source de données V8 n'a **aucun
équivalent confirmé côté V9** (ni dans `docs/architecture/CONTEXT_CONTRACT.md`, ni dans les
couches Scènes/Comportements/Fenêtres) — par opposition à la classe **B** (réécrire), qui
s'applique dès qu'une donnée V9 équivalente existe et qu'il suffit d'écrire de vraies
`conditions:` (cas des 3 YAML refactorés en Phase 9.8 B4 : GRAMMAR_BREAK, GRAMMAR_CONTEXTE,
GRAMMAR_PULLBACK).

L'archivage n'est **pas une suppression** : le fichier reste versionné, lisible, et
réintégrable (`git mv` inverse) dès qu'une donnée V9 source apparaît — cohérent avec CHARTE
Règle 3 (« la mémoire sert d'abord à conserver »), qui s'applique aussi aux principes eux-mêmes,
pas seulement aux champs de contexte (cf. DOCTRINE.md Règle 27 reformulée, Phase 9.8 B2).

## Entrées archivées

| Fichier | Archivé le | Origine V8 | Motif (classe C) |
|---|---|---|---|
| `GRAMMAR_GRAVITE.yaml` | 2026-07-08 | `pf_relational_gravity_probe` | Aucun champ V9 équivalent dans `CONTEXT_CONTRACT.md` ni dans les couches Scènes/Comportements. `conditions: []`, `bounds: {}` — jamais eu de logique déclarative écrite, contrairement aux 3 YAML refactorés en B4 qui avaient des notes de conditions déjà rédigées. |
| `GRAMMAR_INVERSION.yaml` | 2026-07-08 | `pf_tick_cycle_detector` | Même réserve : aucune donnée V9 confirmée. `GRAMMAR_ANTAGONISME` et `GRAMMAR_CROISEMENT` partagent cette source V8 mais **ne sont pas archivés dans ce livrable** — ils restent dans `core/v9/principles/` en l'état, à ré-auditer séparément (périmètre B5 strictement limité à GRAVITE + INVERSION, voir note dans `GRAMMAR_INVERSION.yaml`). |

## Non-régression

- `config.PRINCIPLE_ACTIVE_IDS` n'a jamais inclus ces 2 IDs (les deux étaient `v9_status:
  SHADOW` avant l'archivage) — l'archivage ne change donc aucun comportement de signal ACTIF.
- `tests/test_archived_yamls_not_in_active_ids.py` verrouille structurellement ce fait.
- Catalogue actif : 27 → **25** principes (9 `node_rule` + 16 `grammar`, dont 15 SHADOW + 1
  ACTIVE = GRAMMAR_REGIME). Voir `tests/test_principle_engine.py` (comptages mis à jour Phase
  9.8 B5) et `docs/DOCTRINE.md` Règle 11.

## Procédure de réintégration (si une donnée V9 apparaît un jour)

1. `git mv core/v9/principles/_archive/<FICHIER>.yaml core/v9/principles/<FICHIER>.yaml`
2. Retirer les champs `archived` / `archived_at` / `archived_reason` du YAML
3. Écrire de vraies `conditions:` (référencer le champ V9 nouvellement PROPAGÉ dans
   `CONTEXT_CONTRACT.md`)
4. Mettre à jour cette entrée du manifeste (déplacer vers un futur tableau « Réintégrations »)
5. Mettre à jour les comptages `tests/test_principle_engine.py` et `docs/DOCTRINE.md` Règle 11
6. Entrée `DECISIONS_LOG.md` documentant la réintégration
