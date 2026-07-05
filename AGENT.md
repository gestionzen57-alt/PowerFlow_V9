# AGENT.md — PowerFlow V9

## Statut
Document racine du système PowerFlow V9.

## Mission
PowerFlow V9 est un système de lecture comportementale des forces de marché.
Il observe, structure, mémorise, confronte et qualifie les dynamiques de marché
avant toute logique d'exploitabilité ou d'exécution.

## Priorité absolue
1. Fidélité de lecture
2. Cohérence comportementale
3. Mémoire et confrontation replay
4. Qualification des fenêtres
5. Exploitabilité
6. Exécution éventuelle

## Phrase directrice
Ne jamais demander au système de trader ce qu'il ne sait pas encore décrire.

## Ordre cognitif officiel
1. Forces
2. Scènes
3. Comportements
4. Fenêtres
5. Exploitabilité
6. Exécution éventuelle

## Interdits
- Ne pas sauter directement vers signal / trade / optimisation.
- Ne pas remplacer la perception par une logique de scoring prématurée.
- Ne pas introduire un outil ou une architecture sans préciser sa place dans la chaîne cognitive.
- Ne pas hériter implicitement de V8, Hermes legacy, Bash legacy ou workflows non audités.
- Ne pas confondre mémoire de lecture et mémoire d'exécution.

## Entrées principales
- Forces multi-devises MT4/SDI
- Structure multi-timeframe
- Tick lecture complémentaire MT5
- Zones
- Fenêtres
- Historique de scènes
- Mémoire comportementale
- Replay validé

## Sorties principales
- Lecture structurée de forces
- Scène courante
- Comportement qualifié
- Statut de fenêtre
- Niveau d'exploitabilité
- Rapport synthétique
- Mise à jour mémoire

## Routing conceptuel
### Si la tâche concerne la perception
router vers :
- force-reader
- scene-builder
- behavior-analyst

### Si la tâche concerne la confrontation
router vers :
- replay-confronter
- reviewer

### Si la tâche concerne la qualification
router vers :
- window-gate
- exploitability-gate

### Si la tâche concerne la doctrine
router vers :
- doctrine-keeper

## Conditions d'arrêt
Le système s'arrête si :
- la lecture est incomplète
- la scène est ambiguë
- le comportement n'est pas qualifiable
- la fenêtre n'est pas confirmée
- une validation humaine est requise
- un garde-fou est atteint

## Validation humaine obligatoire
Demander HITL si :
- ambiguïté élevée
- comportement nouveau ou contradictoire
- fenêtre sensible
- action irréversible
- conflit entre couches cognitives
- doute sur la fidélité de lecture

## Garde-fous
- max itérations
- stagnation
- budget temps / coût / tokens
- rollback logique
- refus d'exécution si perception non stabilisée

## Références pivots
- docs/DOCTRINE.md (index des 19 règles, renvoie vers docs/doctrine/*.md)
- docs/doctrine/CHARTE_COGNITIVE_V9.md
- docs/doctrine/MEMORY_POLICY_V9.md
- docs/doctrine/ORCHESTRATION_POLICY_V9.md
- docs/doctrine/MIGRATION_POLICY_V9.md
- docs/LEXIQUE.md (index alphabétique, renvoie vers docs/lexicon/LEXICON_V9.md)
- docs/lexicon/LEXICON_V9.md
- docs/ARCHITECTURE.md (vue d'ensemble technique)
- docs/NOMENCLATURE.md (conventions de nommage)
- docs/ROADMAP.md (phases 9-13)
- docs/DOC_GOVERNANCE.md (gouvernance documentaire)
- docs/STATE.md
- docs/CACHE_BOARD.md