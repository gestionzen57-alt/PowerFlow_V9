# LESSONS_LEARNED — leçons opérationnelles

Leçons non doctrinales (comportementales/opérationnelles) apprises en cours de chantier.
Ne pas y mettre de décision de doctrine (voir `DECISIONS_LOG.md` pour ça) ni de bug
technique isolé (voir `../INCIDENTS.md`).

## Sessions concurrentes
Plusieurs sessions Claude Code peuvent travailler simultanément sur des branches de
phase différentes du même dépôt (constaté 2026-07-05 : fast-forward local de
`feat/v9-phase4-comportements` pendant qu'une autre session était active). Avant de
supposer qu'un fichier « dirty » dans le working tree est un nouveau travail, le diffé
contre les commits connus des branches sœurs (`git diff --no-index`) — il peut s'agir
d'un reliquat redondant d'une session concurrente plutôt que d'un travail en cours à
préserver.

## Cohabitation code / gouvernance documentaire
La gouvernance documentaire (`docs/v9-governance`) a pu avancer en parallèle d'une phase
de code active (Phase 9) sans conflit, en respectant une règle stricte : lecture seule
sur le code en cours, mention explicite « en cours, non finalisé » dans les documents
qui le référencent tant que la phase n'est pas clôturée (`docs/DOC_GOVERNANCE.md`
règle 9). Ce pattern (doc en parallèle, jamais de modification croisée du code d'une
autre session) est reproductible pour de futurs chantiers documentaires concurrents.

## Windows / encodage console
Les scripts Python affichant du français accentué ou des séparateurs box-drawing sur
une console Windows (cp1252 par défaut) doivent forcer
`stream.reconfigure(encoding="utf-8", errors="replace")` sur stdout/stderr en début de
script, avec uniquement la bibliothèque standard (pas de dépendance externe).

## Idempotence des scripts de rejeu
Tout script de régénération/rejeu sur des tables dérivées doit soit disposer d'une
contrainte UNIQUE métier réelle, soit refuser par défaut de s'exécuter sur une DB non
vide (exit non nul), avec une option explicite de purge ciblée (`--replace-derived`) et
un mode d'inspection sans écriture (`--dry-run`). Un identifiant généré avec suffixe
aléatoire ne protège jamais contre un rejeu en double.

## Lecture des principes migrés
Les 27 principes YAML migrés de V8 sont zéro-dépendance et directement portables tels
quels — la valeur ajoutée était dans le portage direct, pas dans une réécriture.
Certains (9/27, type `node_rule`) restent dégradés tant que `zone_diagnostics` n'est
pas alimentée : dégradation gracieuse assumée, jamais une erreur silencieuse.
