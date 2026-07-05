# PHASE 9 — Décision et Principes

## Statut
🔄 **EN COURS** au 2026-07-05, sur une session concurrente à ce chantier documentaire.
Ce fichier est un placeholder d'inventaire — à compléter/valider par la session qui clôt
la phase, en suivant le gabarit de
[docs/checkpoints/CHECKPOINT_TEMPLATE.md](../checkpoints/CHECKPOINT_TEMPLATE.md) et en
mettant à jour [docs/STATE.md](../STATE.md), [docs/ROADMAP.md](../ROADMAP.md) et
[docs/DOC_REGISTRY.yml](../DOC_REGISTRY.yml) en conséquence.

## Ce qui a été constaté (lecture seule, code non commité au moment de la rédaction)

Fichiers présents dans l'arborescence mais non finalisés :
- `core/v9/orchestrator.py` — étend `run_chain` avec Régime → Principes → Signal → Décision
- `core/v9/regime_db.py` / `regime_detector.py` — table `regime_snapshots`, `RegimeDetector`
- `core/v9/principle_db.py` / `principle_engine.py` — tables `principles` / `principle_evaluations`, `PrincipleEngine`
- `core/v9/signal_db.py` / `signal_generator.py` — table `signals`, `SignalGenerator`
- `core/v9/decision_db.py` / `decision_logger.py` — table `decisions`, `DecisionLogger`
- `core/v9/zone_db.py` — table `zone_diagnostics` (créée, **non alimentée**)
- `core/v9/principles/*.yaml` — 27 principes migrés de V8 (9 `node_rule` + 18 `GRAMMAR_*`)
- `tests/test_regime_detector.py`, `test_principle_engine.py`, `test_decision_logger.py`, `test_signal_generator.py` — 68 tests au total constatés (non comptés dans le total officiel de `docs/STATE.md` tant que la phase n'est pas clôturée)

Détail du schéma : [docs/architecture/DB_SCHEMA.md](../architecture/DB_SCHEMA.md) (sections
marquées « Phase 9, en cours »). Détail de la chaîne :
[docs/architecture/CHAINE_COGNITIVE.md](../architecture/CHAINE_COGNITIVE.md) §6.

## Gaps connus (documentés dans le code au 2026-07-05)
- `zone_diagnostics` créée mais aucun détecteur ne l'alimente — 9 des 27 principes
  (`node_rule`, ex. `ZONE_RETEST`, `NODE_BIRTH_FAST`) sont évalués mais ne se déclenchent
  jamais tant que cette table est vide (dégradation gracieuse, pas d'erreur). Chantier
  distinct estimé 5-8 jours, volontairement hors scope de cette phase.
- `regime_snapshots.cassure_type` reste toujours `INDETERMINEE` (pas de couche tick en V9).
- Seulement 10 des 27 principes sont routés en mode ACTIVE ; les 17 autres sont en mode
  SHADOW (journalisés, jamais routés vers un signal).

## À compléter à la clôture de la phase
- [ ] Décisions de design assumées (pourquoi ces 10 principes ACTIVE plutôt que d'autres, pourquoi ces seuils de régime)
- [ ] Écarts vis-à-vis de la doctrine ou des formats, s'il y en a
- [ ] Nombre de tests final et delta vs 139 (Phases 1-8)
- [ ] Mise à jour de [docs/LEXIQUE.md](../LEXIQUE.md) et `docs/lexicon/LEXICON_V9.md` (les termes Régime/Principe/Signal/Décision/Zone extrême y sont déjà provisoirement définis, à confirmer/corriger contre le code final)
- [ ] Mise à jour de [docs/DOCTRINE.md](../DOCTRINE.md) règles 11 et 12 (statut « en cours » à retirer)
- [ ] Checkpoint dédié dans `docs/checkpoints/`
