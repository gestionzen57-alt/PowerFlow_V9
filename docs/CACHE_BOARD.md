# CACHE_BOARD — PowerFlow V9

## Rôle
Ce fichier est le tableau de bord compact de reprise.
Il doit pouvoir être relu en 2 minutes maximum au début de chaque session.

## Statut global
- Projet : PowerFlow V9
- Nature : refondation cognitive + architecture propre
- Base : dossier V9 vide
- Source de vérité : GitHub
- Doctrine : architecture-first
- État : Phase 2A LIVRÉE — EA MT4 reconstruits (V9_Sonde_TF, V9_Sonde_M1) sur `feat/v9-phase2-ea-mt4`. Phase 1 (6 formats) terminée et fusionnée sur `feat/v9-foundation-clean`.

## Décision fondatrice
V9 part de zéro.
Aucune mémoire, aucun skill, aucune convention, aucun workflow ancien n'est repris implicitement depuis V8/Hermes.

## Mission produit
Construire un système qui comprend les forces dans leur lecture :
- globale
- temporelle
- zonale
- multi-devises
- fenêtrée
- orchestrée
- fractale
- comportementale

## Ordre cognitif officiel
1. Forces
2. Scènes
3. Comportements
4. Fenêtres
5. Exploitabilité
6. Exécution éventuelle

## Ce que le projet n'est pas
- pas une simple migration technique
- pas un bot de signal prioritaire
- pas un projet RAG en premier
- pas une accumulation de modules
- pas une extension sale de V8

## Ce que le projet doit devenir
- une base saine
- une mémoire fiable
- une doctrine stable
- un squelette agentique propre
- une machine de confrontation / replay / apprentissage continu

## Chantiers actifs
- [A] Doctrine fondatrice V9 ✅
- [B] Structure repo propre ✅
- [C] Politique mémoire V9 — contrat Forces ↔ Scènes posé (MEMORY_CONTRACT.md) ✅, reste à étendre aux couches aval
- [D] Inventaire de migration V8 → V9
- [E] AGENT.md racine V9
- [F] Lexique natif V9 ✅
- [G] Formats couche Forces ✅ (FORMAT_FORCES.md)
- [H] Formats couche Scènes ✅ (FORMAT_SCENES.md)
- [I] Formats couches Comportements / Fenêtres / Exploitabilité ✅ (livrés 2026-07-05, branche `feat/v9-phase1-formats-aval`)
- [J] Corrections post-review (scene_source, schema_version, contrat mémoire aval) ✅
- [K] Phase 2A — EA MT4 (V9_Sonde_TF, V9_Sonde_M1) ✅ (livrés 2026-07-05, branche `feat/v9-phase2-ea-mt4`)

## Risques ouverts
- dérive vers des solutions techniques prématurées
- contamination par anciennes mémoires Hermes
- confusion V8 / V9
- multiplicité des docs sans synchronisation
- perte de fil due aux limites de contexte

## Garde-fous
- Git = source de vérité
- STATE.md tenu à jour
- checkpoint à chaque jalon important
- cache board relu à chaque session
- migration par audit, jamais par héritage implicite

## Prochaines 3 actions
1. Merger `feat/v9-phase2-ea-mt4` puis Phase 2B — bridge DB (réception TCP côté Python, stockage, lecteur réel)
2. Rédiger AGENT.md racine V9
3. Lancer l'inventaire de migration V8 → V9

## Références pivots
- docs/doctrine/CHARTE_COGNITIVE_V9.md
- docs/STATE.md
- docs/checkpoints/CHECKPOINT_2026_07_05_V9_INIT.md
- docs/checkpoints/CHECKPOINT_2026_07_05_V9_PHASE1A.md
- docs/checkpoints/CHECKPOINT_2026_07_05_V9_PHASE1B.md
- docs/checkpoints/CHECKPOINT_20260705_V9_PHASE2A.md
- ea/V9_Sonde_README.md
- docs/architecture/formats/FORMAT_FORCES.md
- docs/architecture/formats/FORMAT_SCENES.md
- docs/architecture/formats/MEMORY_CONTRACT.md
- docs/architecture/formats/FORMAT_COMPORTEMENTS.md
- docs/architecture/formats/FORMAT_FENETRES.md
- docs/architecture/formats/FORMAT_EXPLOITABILITE.md
