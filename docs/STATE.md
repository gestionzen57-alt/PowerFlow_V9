# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-05

## Statut
PHASE 1 EN COURS DE CORRECTION — 6 formats spécifiés (amont + aval), corrections post-review en cours de fusion

## Résumé exécutif
PowerFlow V9 est lancé comme une refondation propre depuis un dossier vide.
Le projet vise à éliminer la dette de structure, la confusion documentaire et les biais hérités de V8/Hermes.
La doctrine de départ impose une architecture centrée sur la lecture des forces avant toute couche d'exploitabilité.
La Phase 1 (squelette cognitif) a produit les formats JSON des 5 couches (Forces, Scènes, Comportements, Fenêtres, Exploitabilité) ainsi que le contrat de mémoire associé.

## Livrables Phase 1A (session parallèle A)
- docs/architecture/formats/FORMAT_FORCES.md — format de sortie de la couche Forces (8 devises, 7 timeframes dont M1 séparé, STALE_GATE)
- docs/architecture/formats/FORMAT_SCENES.md — format de sortie de la couche Scènes (zone, coalitions, antagonismes, cinématique locale, confluences MTF)
- docs/architecture/formats/MEMORY_CONTRACT.md — contrat de mémoire Forces ↔ Scènes (cycle hypothèse → validation/rejet)

## Livrables Phase 1B (session parallèle B)
- docs/architecture/formats/FORMAT_COMPORTEMENTS.md
- docs/architecture/formats/FORMAT_FENETRES.md
- docs/architecture/formats/FORMAT_EXPLOITABILITE.md

## Décisions actées
- V9 part dans un dossier vide.
- GitHub est la source de vérité.
- V8 devient une source de migration curée, pas une base de travail directe.
- La mémoire V9 sera reconstruite proprement.
- Le squelette cognitif officiel est :
  Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Exécution éventuelle.
- Les documents pivots doivent être créés avant tout chantier de code.
- Les formats JSON des couches Comportements, Fenêtres et Exploitabilité sont spécifiés (session parallèle B, branche `feat/v9-phase1-formats-aval`) : `docs/architecture/formats/FORMAT_COMPORTEMENTS.md`, `FORMAT_FENETRES.md`, `FORMAT_EXPLOITABILITE.md`. Chaque format référence explicitement sa couche amont ; aucune logique d'exécution d'ordre n'y figure.
- La revue CEO des 6 formats a validé le fond mais a identifié 3 corrections (scene_source de Comportements, schema_version manquant sur les 3 formats amont, contrat mémoire non étendu aux couches aval) — traitées sur la branche `fix/v9-phase1-review`.

## Objectif immédiat
Poser une fondation documentaire, cognitive et structurelle stable pour pouvoir ensuite orchestrer proprement Claude Code et Hermes sur V9.

## Chantiers en file
1. Corrections post-review et fusion des 6 formats vers main (Phase 1, clôture)
2. AGENT.md racine V9
3. Inventaire de migration V8 → V9
4. Structure skills / agents / assets / runtime
5. Phase 2 — Couche Forces (lecteur réel, EA, bridge DB)

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
Appliquer les 3 corrections post-review, fusionner les 6 formats vers main, puis engager la Phase 2 — Couche Forces (implémentation).
