# CHECKPOINT_2026_07_05_V9_PHASE1A

## Contexte
Session parallèle A de la Phase 1 (squelette cognitif) de PowerFlow V9.
Objectif : définir les formats JSON et interfaces des couches amont (Forces, Scènes) et le contrat de mémoire associé, sans coder aucun module métier.

## Décisions prises
- Le format de sortie de la couche Forces est un snapshot daté, séparant strictement le candle-close (`forces`, timeframes M5/M15/M30/H1/H4/D1) du tick/vélocité (`m1`).
- Chaque entrée de force porte sa propre fraîcheur (`freshness`) ; un STALE_GATE bloquant est défini avec des seuils de péremption par timeframe.
- Le format de sortie de la couche Scènes référence son snapshot de forces source sans jamais dupliquer les données brutes, et assemble zone, coalitions, antagonismes, cinématique locale, confluences MTF et contexte temporel.
- Le contrat de mémoire pose un cycle de vie unique pour toute entrée : hypothèse (`memory_temp.md`) → validation (`memory.md`) ou rejet (archive), avec justification obligatoire à la sortie de l'état hypothèse.
- Règle actée : la mémoire sert d'abord la perception, jamais l'exécution.
- Règle actée : on ne migre que des connaissances validées, jamais une mémoire brute ou une hypothèse.

## Livrables produits
- docs/architecture/formats/FORMAT_FORCES.md
- docs/architecture/formats/FORMAT_SCENES.md
- docs/architecture/formats/MEMORY_CONTRACT.md

## Validation effectuée
- Les 3 fichiers existent et sont commités.
- Tous les blocs JSON des 3 documents ont été validés syntaxiquement (parsing Python `json.loads` sans erreur).
- Le vocabulaire natif du LEXICON_V9.md est respecté (force, scène, zone, coalition, antagonisme, cinématique, mémoire de lecture).
- Aucune couche aval (Comportements, Fenêtres, Exploitabilité, Exécution) n'est référencée comme dépendance dans les 3 documents.
- Aucune référence à V8.
- Aucune logique de trading ou d'exécution introduite.

## Ce qui reste explicitement hors scope de cette session
- Formats des couches Comportements, Fenêtres, Exploitabilité (chantiers 1.3 à 1.5 de la roadmap).
- Toute implémentation Python réelle des lecteurs/constructeurs.
- Tout travail sur l'EA MT4, le bridge DB ou la Phase 2.

## Prochaine marche
- Spécifier le format de la couche Comportements (chantier 1.3).
- Spécifier le format de la couche Fenêtres (chantier 1.4).
- Spécifier le format de la couche Exploitabilité (chantier 1.5).
- Étendre le contrat de mémoire à ces couches une fois leurs formats posés.

## Risque principal
Que les formats des couches aval soient spécifiés par une autre session sans relecture stricte de FORMAT_FORCES.md et FORMAT_SCENES.md, introduisant une incohérence de vocabulaire ou une dépendance implicite mal formée.

## Contre-mesure
Toute session future spécifiant Comportements/Fenêtres/Exploitabilité doit relire ces 3 documents avant d'écrire, et référencer explicitement `forces_snapshot_ref` / `scene_id` selon le même principe de référence sans duplication.
