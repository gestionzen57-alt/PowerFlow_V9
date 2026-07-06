# Checkpoint documentaire — nettoyage des documents stales après stabilisation live Phase 9

Date : 2026-07-06 12:21 CEST  
Périmètre : documentation / gouvernance / continuité  
Branche de référence : `feat/v9-foundation-clean`

## Objet

Ce checkpoint acte que l'information documentaire « `zone_diagnostics` créée mais non alimentée » est désormais périmée au regard de l'état live et des vérifications récentes. Le code, la base live et les vérifications Hermes confirment que `zone_diagnostics` est alimenté, exploitable, et qu'il ne constitue plus l'explication du non-déclenchement de `ANTAGONIST_NODE`. [file:364]

## Constat acté

Les éléments suivants sont désormais considérés comme acquis :

- Le flux live réel Phase 9 est confirmé et la chaîne cognitive complète tourne en conditions réelles. [file:418]
- `zone_diagnostics` est alimenté en live, avec des lignes présentes en base et plusieurs états de zone visibles selon le rapport de vérification. [file:418]
- `ANTAGONIST_NODE` ne dépend pas de `zone_diagnostics`, mais du contexte cross-TF issu de `forces_snapshots`, et son non-déclenchement observé est cohérent avec un marché aligné H1/M5. [file:418]
- Le message final de calibration suggérant un blocage par le gap `zone_diagnostics` est un résidu obsolète et ne doit plus être repris comme vérité métier. [file:418]

## Rupture de continuité documentaire

Plusieurs documents continuent encore d'indiquer que `zone_diagnostics` est « créée mais non alimentée ». Cette formulation est désormais en divergence avec l'état réel vérifié du système et doit être nettoyée dans un chantier documentaire borné, distinct d'un chantier code. [file:364][file:418]

## Documents à mettre à jour

Le rapport Hermes a signalé au moins les documents suivants comme stales : [file:418]

| Document | Nature de l'écart | Action attendue |
|---|---|---|
| `README.md` | Mention ancienne sur `zone_diagnostics` non alimentée | Aligner sur l'état live actuel |
| `docs/CACHE_BOARD.md` | Reprise de l'ancien gap comme état courant | Mettre à jour le statut réel |
| `docs/ARCHITECTURE.md` | Continuité architecture/documentation obsolète | Corriger la dépendance réelle |
| `docs/ROADMAP.md` | Gap présenté comme toujours ouvert en l'état | Reformuler en historique ou lever si clos |
| `docs/DB_SCHEMA.md` | Description potentiellement dépassée | Refléter l'usage live réel |
| `docs/CHAINE_COGNITIVE.md` | Description fonctionnelle à réaligner | Intégrer l'alimentation effective |
| `docs/phases/PHASE9_DECISION.md` | Phase 9 documentée avec ancien état | Mettre à jour le bilan de phase |
| `docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md` | Checkpoint antérieur devenu partiellement périmé | Ajouter mention de dépassement daté |

## Règle de mise à jour

La mise à jour doit suivre la hiérarchie documentaire du projet : état réel du code et des fichiers d'abord, puis documents pivots, puis documents de synthèse. Le nettoyage ne doit pas rouvrir Phase 10, ni mélanger observation live et architecture agents. [file:364][file:313]

## Décision

Décision structurante : ouvrir un **checkpoint documentaire de nettoyage** pour aligner tous les documents stales sur la réalité suivante :

- Phase 9 live est stabilisée à un niveau suffisant pour la calibration continue. [file:418]
- `zone_diagnostics` n'est plus à documenter comme « non alimentée » dans l'état courant. [file:418]
- `ANTAGONIST_NODE = 0` n'est pas un bug documentable, mais un comportement normal de marché dans le contexte observé. [file:418]

## Ce qui reste gelé

Les éléments suivants restent explicitement hors périmètre de ce checkpoint documentaire :

- Ouverture de la Phase 10 — fédération d'agents. [file:364][file:313]
- Architecture globale agents / routing / mémoire avancée. [file:364]
- Skills auto-générés. [file:364][file:313]
- Toute modification d'exécution d'ordres avant la phase prévue par doctrine. [file:418]

## Prochaine action unique

Créer puis exécuter un lot borné de mises à jour documentaires sur les fichiers signalés stales, avec validation finale par checkpoint ou mise à jour de `docs/STATE.md` si le projet l'exige. [file:364][file:313]
