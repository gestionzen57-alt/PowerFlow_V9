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

## Autopilot CEO 2026-07-13 — go fait tout, tu orchestres

Quand le CEO mandate « autopilot », le bon réflexe n'est PAS de tout faire
en un seul commit / une seule nuit. Le chantier 12-17 jours estimé pour
les 6 actions prioritaires (P1+P2+P3+P4+P5+P6) ne tient pas dans une
session autopilot responsable — R8/R22/R26 (backup MD5 par `core/v9/*`
modifié, 1 commit par chantier, tests verts entre chaque) imposent un
découpage. Action concrète : livrer les chantiers courts + reportés
indépendants dans la même session (P6 module pur neuf + P1 signal porte
recommandation + fix test obsolète), reporter P2/P3/P4/P5 dans une file
d'attente explicite doc dans `logs/autopilot_status.md`. Pattern
reproductible : (a) journal d'état local créé en 1er (pas de Telegram
status promis qu'on ne peut pas tenir), (b) livrables R8-clean avec
backups MD5 + commits atomiques + pytest --ignore des dettes pré-existantes
connues, (c) DECISIONS_LOG + ACTIVE_TASKS + STATE mis à jour pour rendre
la session restartable côté Perplexity/Claude Code sans perdre le fil.

Limite Telegram runtime : `config/telegram.json` contient souvent un
placeholder sanitisé (`8932306765:***` visible dans la config committée).
Le vrai token vit dans env var d'un daemon externe, inaccessible depuis
Hermes. Test direct `getMe` → HTTP 404 le confirme honnêtement. R6
appliquée : status local dans `logs/autopilot_status.md`, pas de
simulation d'un envoi Telegram qui n'a pas eu lieu.
