# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-05

## Statut
PHASE 2 TERMINÉE — EA MT4 (V9_Sonde_TF, V9_Sonde_M1) et capture Python (STALE_GATE, ForcesReader, capture_server, db_schema) fusionnés sur `feat/v9-foundation-clean`. Seuils STALE_GATE harmonisés (config.py fait foi). Phase 1 (6 formats) terminée et fusionnée précédemment.

## Résumé exécutif
PowerFlow V9 est lancé comme une refondation propre depuis un dossier vide.
Le projet vise à éliminer la dette de structure, la confusion documentaire et les biais hérités de V8/Hermes.
La doctrine de départ impose une architecture centrée sur la lecture des forces avant toute couche d'exploitabilité.
La Phase 1 (squelette cognitif) a produit les formats JSON des 5 couches (Forces, Scènes, Comportements, Fenêtres, Exploitabilité) ainsi que le contrat de mémoire associé. Les 3 corrections identifiées en revue CEO ont été appliquées et fusionnées.
La Phase 2A a reconstruit la sonde EA MT4 (couche Forces, capture brute) from scratch, en auditant les bugs connus de V8 pour ne pas les reproduire.
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

## Livrables Phase 2A — EA MT4 (branche `feat/v9-phase2-ea-mt4`)
- ea/V9_Sonde_TF.mq4 — sonde candle-close multi-timeframe (1 instance par TF M5/M15/M30/H1/H4/D1), JSON aligné FORMAT_FORCES.md
- ea/V9_Sonde_M1.mq4 — sonde M1 dédiée, mode tick/vélocité (OnTick, pas de timer), fenêtre glissante 5s, vitesse par devise
- ea/V9_Sonde_README.md — procédure de compilation, déploiement, vérification, diagnostic buffers SDI
- Audit du code V8 (`EA_PowerFlow_V8_Sonde_TF.mq4`, `EA_PowerFlow_V8_UniversalSonde.mq4` + archives de bugs) : aucune inversion confirmée du buffer AUD dans le code EA lui-même (l'ordre 0=AUD,1=GBP,2=JPY,3=USD,4=CAD,5=EUR,6=CHF,7=NZD est une propriété vérifiée de l'indicateur SDI, pas un bug de lecture) — les inversions documentées en V8 concernaient soit une période de données corrompue (EA legacy hardcodant PERIOD_M1 pour tous les TF), soit une interprétation comportementale en aval. Buffers rendus configurables via inputs par sécurité.
- Bugs V8 corrigés par construction en V9 : décalage horaire broker→UTC non appliqué (nouvel input `BrokerUTCOffsetHours`), EA HTF lisant PERIOD_M1 hardcodé (V9 utilise systématiquement `Period()` réel), ShiftIndex mal aligné (M1 et candle-close strictement séparés dans deux fichiers distincts).

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
- Phase 2 close par fusion des branches `feat/v9-phase2-ea-mt4` et `feat/v9-phase2-python-capture` sur `feat/v9-foundation-clean`. 3 points ouverts tranchés à cette occasion : (1) seuils STALE_GATE — `config.py` fait foi, `FORMAT_FORCES.md` mis à jour en conséquence (M5=35s, M15=95s, M30=185s, H1=365s, H4=1450s/24min, D1=9000s/2h30) ; (2) port TCP 31685 conservé comme port de référence V9, avec note explicite dans `config.py` sur le conflit avec V8 en production (basculer sur 31690 pour tester en parallèle) ; (3) `V9_Sonde_M1.mq4` étant désormais livré, les hypothèses de forme du message M1 dans `forces_reader.py` (mode tick_velocity, mêmes clés `force_*`) restent à revalider empiriquement dès la première capture réelle, mais ne bloquent plus la clôture de Phase 2.

## Objectif immédiat
Engager la Phase 3 — Couche Scènes (lecteur réel). La validation terrain de la chaîne EA MT4 → capture_server.py → v9_forces.db reste un chantier ouvert, non bloquant pour démarrer la Phase 3.

## Chantiers en file
1. Phase 3 — Couche Scènes (lecteur réel)
2. Validation terrain de la sonde EA (ea/V9_Sonde_TF.mq4) avec capture_server.py
3. AGENT.md racine V9
4. Inventaire de migration V8 → V9
5. Structure skills / agents / assets / runtime

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
Phase 3 — Couche Scènes (lecteur réel). La validation terrain (chart MT4 réel avec ea/V9_Sonde_TF.mq4 sur capture_server.py, port 31685) peut être menée en parallèle, sans bloquer le démarrage de la Phase 3.
