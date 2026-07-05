# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-05

## Statut
INIT — Fondation en cours

## Résumé exécutif
PowerFlow V9 est lancé comme une refondation propre depuis un dossier vide.
Le projet vise à éliminer la dette de structure, la confusion documentaire et les biais hérités de V8/Hermes.
La doctrine de départ impose une architecture centrée sur la lecture des forces avant toute couche d'exploitabilité.

## Décisions actées
- V9 part dans un dossier vide.
- GitHub est la source de vérité.
- V8 devient une source de migration curée, pas une base de travail directe.
- La mémoire V9 sera reconstruite proprement.
- Le squelette cognitif officiel est :
  Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Exécution éventuelle.
- Les documents pivots doivent être créés avant tout chantier de code.

## Objectif immédiat
Poser une fondation documentaire, cognitive et structurelle stable pour pouvoir ensuite orchestrer proprement Claude Code et Hermes sur V9.

## Chantiers en file
1. Charte cognitive V9
2. Cache board V9
3. Checkpoint init V9
4. Politique mémoire V9
5. AGENT.md racine V9
6. Inventaire de migration V8 → V9
7. Structure skills / agents / assets / runtime

## Contraintes connues
- Limite de contexte / messages côté assistant
- Besoin de checkpoints persistants
- Volonté d'éviter toute confusion de version
- Préférence forte pour architecture avant code
- Détestation de la gestion manuelle Git par l'utilisateur

## Rôles opérationnels
- Perplexity : doctrine, orchestration, structure, checkpoints, continuité
- Claude Code : implémentation structurée
- Hermes free : support ciblé / itérations légères / expérimentations encadrées

## Règle d'or
Aucune implémentation structurante ne doit être lancée sans ancrage explicite dans la doctrine V9.

## Prochaine étape recommandée
Créer physiquement les fichiers et dossiers de fondation dans le repo V9, puis rédiger le brief Claude Code pour poser l'ossature initiale sans dette.