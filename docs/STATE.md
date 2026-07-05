# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-05

## Statut
PHASE 2B EN COURS — capture Python + STALE_GATE + forces_reader livrés sur `feat/v9-phase2-python-capture`

## Résumé exécutif
PowerFlow V9 est lancé comme une refondation propre depuis un dossier vide.
Le projet vise à éliminer la dette de structure, la confusion documentaire et les biais hérités de V8/Hermes.
La doctrine de départ impose une architecture centrée sur la lecture des forces avant toute couche d'exploitabilité.
La Phase 1 (squelette cognitif) a produit les formats JSON des 5 couches (Forces, Scènes, Comportements, Fenêtres, Exploitabilité) ainsi que le contrat de mémoire associé. Les 3 corrections identifiées en revue CEO ont été appliquées et fusionnées.
La Phase 2B (implémentation Python de la couche Forces) a produit le serveur de capture TCP asyncio, le STALE_GATE bloquant, le lecteur de transformation (ForcesReader) et le schéma DB v9_forces.db, avec 15 tests unitaires. Écrit from scratch, sans reprise de code V8.

## Livrables Phase 2B (session `feat/v9-phase2-python-capture`)
- core/v9/config.py — configuration centrale (DB_PATH, ports, seuils STALE_GATE, calibration ForcesReader)
- core/v9/stale_gate.py — StaleGate bloquant (marque stale, ne supprime jamais)
- core/v9/forces_reader.py — transformation JSON brut EA → format V9 (direction, vitesse, croisement, recroisement, rejet_repulsion, compression_extension)
- core/v9/capture_server.py — serveur TCP asyncio port 31685 (--status, --once)
- core/v9/db_schema.py — schéma SQLite forces_snapshots (WAL, busy_timeout 30s)
- tests/test_stale_gate.py, tests/test_forces_reader.py — 15 tests, tous verts
- Voir docs/checkpoints/CHECKPOINT_20260705_V9_PHASE2B.md pour le détail complet (décisions de design, écarts assumés, points ouverts)

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
- La revue CEO des 6 formats a validé le fond mais a identifié 3 corrections (scene_source de Comportements, schema_version manquant sur les 3 formats amont, contrat mémoire non étendu aux couches aval). Ces 3 corrections ont été appliquées sur la branche `fix/v9-phase1-review`, puis fusionnées dans `feat/v9-foundation-clean` (branche de référence de ce dépôt).
- Phase 1 est officiellement close : les 6 formats (FORMAT_FORCES, FORMAT_SCENES, MEMORY_CONTRACT, FORMAT_COMPORTEMENTS, FORMAT_FENETRES, FORMAT_EXPLOITABILITE) sont sur la branche de référence, corrigés et validés.

## Objectif immédiat
Valider en conditions réelles la chaîne EA MT4 (ea/V9_Sonde_TF.mq4) → capture_server.py → v9_forces.db, puis enchaîner sur la couche Scènes (lecteur réel).

## Chantiers en file
1. Validation terrain de la sonde EA (ea/V9_Sonde_TF.mq4, hors scope de cette session Python) avec capture_server.py
2. AGENT.md racine V9
3. Inventaire de migration V8 → V9
4. Structure skills / agents / assets / runtime
5. Phase 3 — Couche Scènes (lecteur réel)

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
Brancher un chart MT4 réel avec ea/V9_Sonde_TF.mq4 sur capture_server.py (port 31685) pour valider la chaîne de bout en bout, puis engager la Phase 3 — Couche Scènes.
