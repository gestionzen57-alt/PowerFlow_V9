# PHASE 9 — Décision et Principes

## Statut
✅ Terminée, branche `feat/v9-foundation-clean` (commit `a233abb` pour le code, canonisée
documentairement le 2026-07-05 par le chantier `docs/v9-governance`). Développée sur une
session concurrente à la gouvernance documentaire ; ce document remplace le placeholder
d'inventaire rédigé pendant que la phase était encore en cours (voir
[docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md](../checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md)
pour le contexte complet de clôture).

## Objectif
Étendre la chaîne cognitive au-delà de l'Exploitabilité avec une couche de décision
qualitative, fondée sur une migration curée des principes de trading V8 — jamais un signal
d'exécution direct (voir [DOCTRINE.md](../DOCTRINE.md) règle 11).

## Chaîne étendue
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → **Régime → Principes → Signal
→ Décision**. Chaque étape ajoutée est isolée par try/except dans `orchestrator.run_chain`
(même pattern fail-soft que les couches 1-5, doctrine règle 6).

## Livrables
- `core/v9/regime_db.py` / `regime_detector.py` — table `regime_snapshots`, `RegimeDetector` :
  machine à états (NEUTRE/PALIER/CASSURE/EXTENSION/RETOUR_EQUILIBRE/REJET) portée de
  `pf_regime_detector.py` (V8), sur fenêtre glissante `REGIME_LOOKBACK_BARS=20` plutôt qu'un
  batch historique. Gap V8 comblé (`regime_snapshots`, 327k lignes en V8, absent de V9 avant
  cette phase — voir [audit_v8_v9_migration.md](../architecture/audit_v8_v9_migration.md) §2.3).
- `core/v9/principle_db.py` / `principle_engine.py` — tables `principles` / `principle_evaluations`,
  `PrincipleEngine` : 27 grammaires YAML migrées **telles quelles** depuis V8
  (`core/v9/principles/*.yaml`, 9 `kind: node_rule` + 18 `kind: grammar`), chacune une fonction
  pure entrée → bool + confiance. 10 principes routés en mode ACTIVE
  (`config.PRINCIPLE_ACTIVE_IDS`), 17 en mode SHADOW (journalisés, jamais routés vers un
  signal).
- `core/v9/signal_db.py` / `signal_generator.py` — table `signals`, `SignalGenerator` : vote
  majoritaire sur les principes ACTIVE déclenchés, filtré par exploitabilité et régime.
- `core/v9/decision_db.py` / `decision_logger.py` — table `decisions`, `DecisionLogger` :
  contexte complet replayable (scène/comportement/fenêtre/exploitabilité/régime/signal),
  action qualitative parmi `observer` / `surveiller` / `preparer_entree` / `aucune_action` —
  jamais un ordre.
- `core/v9/zone_db.py` — table `zone_diagnostics`, schéma migré de V8 (36 808 lignes en
  production V8). **Créée mais non alimentée** cette phase — voir section Gaps.
- `core/v9/orchestrator.py` — `run_chain` étendu avec les 4 étapes Régime/Principes/Signal/
  Décision.
- `scripts/v9_dashboard.py` (`--watch signals`/`--watch decisions` + section chaîne étendue),
  `scripts/v9_calibration.py` (`--principes` : hit rate/confiance/suggestions de promotion
  ACTIVE ou de blocage par le gap `zone_diagnostics`).
- `tests/test_regime_detector.py` (10), `tests/test_principle_engine.py` (36),
  `tests/test_signal_generator.py` (17), `tests/test_decision_logger.py` (12) — 75 nouveaux
  tests.

## Décisions de design assumées
- **Commencer par 10 principes ACTIVE sur 27** plutôt que les 27 d'un coup (conforme à
  [ROADMAP.md](../ROADMAP.md) §Phase 9 : « commencer par les 5-10 principes les plus
  significatifs »). Les 17 SHADOW restent évalués et journalisés (traçabilité complète), mais
  ne peuvent jamais influencer un signal — dégradation par construction, pas par bug.
- **`RegimeDetector` en fenêtre glissante** plutôt qu'en batch historique complet (contrainte
  V9 : orchestrateur événementiel par snapshot, pas de recalcul global). La machine à états
  elle-même est identique à V8.
- **`zone_diagnostics` créée mais non alimentée** : décision explicite de ne pas bloquer la
  clôture de Phase 9 sur ce chantier (estimé 5-8 jours, voir audit §8) — dégradation
  gracieuse documentée en dur dans `principle_engine.py` et `zone_db.py`, jamais une erreur.
- **`regime_snapshots.cassure_type` reste `INDETERMINEE`** : V9 n'a pas de couche tick,
  contrairement à V8 qui distinguait les types de cassure via microstructure.
- **Cache process-local du catalogue de principes** (`_YAML_CACHE` dans `principle_engine.py`) :
  le rechargement YAML par snapshot coûtait ~30ms ; nécessaire pour tenir la cible de latence.

## Écarts assumés vis-à-vis de la doctrine ou des formats
- Aucun écart vis-à-vis des formats `FORMAT_*.md` (aucun de ces 4 nouvelles étapes n'a de
  format JSON dédié pré-existant — ce sont des extensions post-Exploitabilité, hors périmètre
  des 6 formats de Phase 1).
- Doctrine règle 12 (« replay et live marqués distinctement dans les décisions ») **résolue le
  2026-07-06** — colonne `source_type` ("live"/"replay") ajoutée aux 8 tables dérivées,
  peuplée par `orchestrator.run_chain(source_type=...)`. Voir
  `docs/checkpoints/CHECKPOINT_20260706_V9_SOURCE_TYPE.md`.

## Gaps connus (au 2026-07-05, vérifiés dans le code)
- **`zone_diagnostics` non alimentée** — 9 des 27 principes (`node_rule`, ex. `ZONE_RETEST`,
  `NODE_BIRTH_FAST`) référencent des champs absents (`state`, `z_extreme_dir`,
  `tension_score`, ...) et ne se déclenchent donc jamais, y compris `ZONE_RETEST` qui fait
  pourtant partie des 10 principes ACTIVE. Dégradation gracieuse confirmée par les tests
  (`test_principle_engine.py`), jamais d'erreur. Chantier distinct estimé 5-8 jours
  (priorité 2 de l'audit V8→V9), non commencé.
- **Replay vs live** — résolu le 2026-07-06 (colonne `source_type` dans les 8 tables
  dérivées, voir doctrine règle 12).
- **`regime_snapshots.cassure_type`** toujours `INDETERMINEE` (pas de couche tick en V9,
  cf. Phase 11 planifiée).
- **Seuils de régime `PROVISIONAL`** (`SEUIL_PALIER`, `SEUIL_CASSURE`, ...) : portés de V8
  sans recalibration sur données V9 réelles (V8 recommandait n≥50 observations avant de
  figer ces seuils).

## Tests
75 nouveaux tests (`test_regime_detector.py` 10, `test_principle_engine.py` 36,
`test_signal_generator.py` 17, `test_decision_logger.py` 12), portant le total à **214 tests,
tous verts** (139 précédents + 75). Revérifié indépendamment lors de la clôture documentaire
(`python -m pytest tests/ -q` → `214 passed`). `scripts/regenerate_chain.py` rejoué sur les
1194 snapshots non-stale existants : 0 erreur, latence moyenne 189,58 ms/snapshot (chaîne
complète 8 couches), sous la cible de 200 ms.

## Prêt pour le market open / à observer ce soir en live
- La chaîne 8 couches tourne bout en bout sans erreur sur données rejouées (1194 snapshots) —
  prête à tourner en live dès l'ouverture du marché.
- À observer en priorité via `scripts/v9_dashboard.py --watch signals` /
  `--watch decisions` : fréquence réelle de déclenchement des 10 principes ACTIVE (certains,
  comme `ZONE_RETEST`, ne se déclencheront jamais tant que `zone_diagnostics` n'est pas
  alimentée — attendu, pas un bug), latence cumulée sur snapshots live réels (vs 189,58 ms en
  replay), et cohérence des actions qualitatives `decisions` avec le comportement/fenêtre
  source.
- Ne pas interpréter l'absence de déclenchement de `ZONE_RETEST` comme une régression : c'est
  le gap `zone_diagnostics` documenté ci-dessus, attendu.

## Voir aussi
- [docs/STATE.md](../STATE.md) — journal détaillé de la session d'implémentation
- [docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md](../checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md) — mega-checkpoint de clôture et de cohérence documentaire
- [docs/architecture/audit_v8_v9_migration.md](../architecture/audit_v8_v9_migration.md) — origine du gap `zone_diagnostics` et des 27 principes
- [docs/ROADMAP.md](../ROADMAP.md) — séquencement Phase 10-13
