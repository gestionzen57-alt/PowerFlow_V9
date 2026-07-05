# CHECKPOINT_2026_07_05_V9_INIT

## Contexte
Décision de lancer PowerFlow V9 comme refondation propre, dans un dossier vide, afin d'éliminer les biais hérités de V8/Hermes et de repartir sur une base cognitive, documentaire et structurelle saine.

## Décisions prises
- V9 sera traité comme un nouveau chantier.
- V8 ne sera pas repris implicitement.
- Toute migration future devra être auditée et classée.
- GitHub devient la source de vérité absolue.
- Un système de reprise de contexte sera maintenu via CACHE_BOARD + STATE + checkpoints.

## Doctrine validée
La finalité première de V9 est la lecture comportementale des forces.
L'ordre cognitif officiel est :
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Exécution éventuelle.

## Livrables fondation préparés
- docs/doctrine/CHARTE_COGNITIVE_V9.md
- docs/CACHE_BOARD.md
- docs/STATE.md
- docs/checkpoints/CHECKPOINT_2026_07_05_V9_INIT.md

## Ce qui est explicitement refusé
- migration sale depuis V8
- reprise non auditée des mémoires Hermes
- empilement d'outils avant doctrine
- confusion documentaire entre anciennes et nouvelles versions

## Prochaine marche
- poser l'arborescence V9 dans le repo
- écrire la politique mémoire
- écrire AGENT.md racine
- préparer l'inventaire de migration V8 → V9
- lancer Claude Code sur l'ossature uniquement

## Risque principal
Que V9 hérite malgré tout d'une logique ancienne via prompts, skills, mémoire ou conventions non documentées.

## Contre-mesure
Forcer toute nouvelle contribution à préciser :
- sa place dans la chaîne cognitive
- sa justification
- sa relation à V8 (aucune / migration / archive / réécriture)