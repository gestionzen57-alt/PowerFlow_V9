# STATE — PowerFlow V9

## Dernière mise à jour
2026-07-05

## Statut
PHASE 2A LIVRÉE — EA MT4 reconstruits proprement (V9_Sonde_TF, V9_Sonde_M1) sur `feat/v9-phase2-ea-mt4`. Phase 1 (6 formats) terminée et fusionnée sur `feat/v9-foundation-clean`.

## Résumé exécutif
PowerFlow V9 est lancé comme une refondation propre depuis un dossier vide.
Le projet vise à éliminer la dette de structure, la confusion documentaire et les biais hérités de V8/Hermes.
La doctrine de départ impose une architecture centrée sur la lecture des forces avant toute couche d'exploitabilité.
La Phase 1 (squelette cognitif) a produit les formats JSON des 5 couches (Forces, Scènes, Comportements, Fenêtres, Exploitabilité) ainsi que le contrat de mémoire associé. Les 3 corrections identifiées en revue CEO ont été appliquées et fusionnées.
La Phase 2A a reconstruit la sonde EA MT4 (couche Forces, capture brute) from scratch, en auditant les bugs connus de V8 pour ne pas les reproduire.

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

## Objectif immédiat
Merger `feat/v9-phase2-ea-mt4` puis poursuivre la Phase 2 — bridge DB (réception TCP, capture Python, stockage) et lecteur réel des forces.

## Chantiers en file
1. Merge `feat/v9-phase2-ea-mt4` vers la branche de référence
2. Phase 2B — bridge DB (serveur TCP Python, table forces, anti-duplicate côté lecture)
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
Merger la Phase 2A (EA MT4), puis engager la Phase 2B — bridge DB (réception TCP côté Python, stockage, lecteur réel des forces).
