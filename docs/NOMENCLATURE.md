# NOMENCLATURE — PowerFlow V9

## Statut
Conventions de nommage, vérifiées contre le code réel le 2026-07-05. Là où le code diverge
d'une convention idéale, la divergence est notée explicitement plutôt que masquée — le code
reste la source de vérité (voir [DOC_GOVERNANCE.md](DOC_GOVERNANCE.md)).

## Fichiers

| Type | Convention | Exemples réels |
|---|---|---|
| Python | snake_case | `capture_server.py`, `scene_builder.py`, `exploitability_evaluator.py` |
| MQL4 (EA) | `V9_Sonde_{Suffix}.mq4` (préfixe projet + PascalCase) | `V9_Sonde_TF.mq4`, `V9_Sonde_M1.mq4` |
| Documentation | SCREAMING_SNAKE_CASE pour les docs pivots, snake_case/PascalCase mixte accepté ailleurs | `STATE.md`, `CHARTE_COGNITIVE_V9.md`, `FORMAT_FORCES.md` |
| Checkpoints | `CHECKPOINT_{YYYYMMDD}_V9_{NOM_COURT}.md` | `CHECKPOINT_20260705_V9_PHASE8.md` |
| Mega-checkpoints (transversaux, plusieurs phases/chantiers) | `CHECKPOINT_{YYYY-MM-DD}_MEGA_V9.md` (date ISO à tirets, se distingue visuellement d'un checkpoint de phase unique) | `CHECKPOINT_2026-07-05_MEGA_V9.md` |
| Fixtures de test | `{objet}_sample.json` | `tests/fixtures/scenes_sample.json` |

## Tables DB (SQLite, `data/v9_forces.db`)

Convention : snake_case, **pluriel** par défaut. Une exception réelle existe (`exploitability`,
singulier — le mot n'a pas de forme plurielle naturelle en français/anglais dans ce contexte ;
ne pas le renommer, c'est un fait établi du schéma, voir [DB_SCHEMA.md](architecture/DB_SCHEMA.md)).

| Table | Pluriel ? |
|---|---|
| `forces_snapshots`, `scenes`, `behaviors`, `windows`, `regime_snapshots`, `principles`, `principle_evaluations`, `signals`, `decisions`, `zone_diagnostics` | oui |
| `exploitability` | non — exception assumée |

## Colonnes DB

snake_case, sans exception observée. Suffixes conventionnels réels :
- `*_ref` : référence vers l'identifiant textuel d'une table amont (ex. `forces_snapshot_ref`, `scene_id_ref`) — jamais une clé étrangère SQL formelle, toujours une référence logique.
- `*_id` : identifiant unique de la ligne elle-même (ex. `scene_id`, `behavior_id`).
- `*_json` : colonne TEXT contenant du JSON sérialisé (ex. `zone_json`, `cinematique_json`).
- `*_detecte` / `*_requise` : colonnes BOOLEAN de détection/condition (ex. `croisement_detecte`, `validation_hitl_requise`).

## Variables et fonctions

snake_case, sans exception observée : `build_scene`, `analyze_scene`, `evaluate_behavior`,
`evaluate_window`, `run_chain`, `check_freshness`, `snapshot_age_seconds`.

## Classes

PascalCase, sans exception observée : `SceneBuilder`, `BehaviorAnalyzer`, `WindowGate`,
`ExploitabilityEvaluator`, `MarketCalendar`, `StaleGate`, `ForcesReader`, `RegimeDetector`
(Phase 9), `PrincipleEngine` (Phase 9), `SignalGenerator` (Phase 9), `DecisionLogger` (Phase 9).

## Constantes

UPPER_CASE, définies dans `core/v9/config.py` : `LISTEN_PORT`, `DB_PATH`, `ENABLE_CHAIN`,
`STALE_THRESHOLDS_MS`, `COALITION_THRESHOLD`, `SEUIL_EXPLOITABLE`, `PRINCIPLE_ACTIVE_IDS`, etc.

## Identifiants métier (formats réels observés dans le code — pas un idéal théorique)

| Identifiant | Format réel | Source |
|---|---|---|
| `snapshot_id` | fourni par l'EA (voir `FORMAT_FORCES.md`), ou généré `v9-{uuid4}` si absent | `forces_reader.py:113` |
| `scene_id` | `scene-{YYYYmmdd-HHMMSS}-{uuid4[:6]}` | `scene_builder.py:592` |
| `behavior_id` | `beh_{YYYYmmddTHHMMSSZ}_{symbol_lower}_{timeframe_lower}_{uuid4[:6]}` | `behavior_analyzer.py:271-273` |
| `window_id` | `win_{compact_ts}_{symbol}_{timeframe}_{uuid4[:6]}` | `window_gate.py:609` |
| `exploitability_id` | `exp_{compact_ts}_{symbol}_{timeframe}_{uuid4[:6]}` | `exploitability_evaluator.py:594` |
| `regime_id` (Phase 9) | `regime_{compact_ts}_{symbol_lower}_{timeframe_lower}_{currency_lower}_{uuid4[:6]}` | `regime_detector.py:298` |
| `signal_id` (Phase 9) | `sig_{compact_ts}_{symbol_lower}_{timeframe_lower}_{uuid4[:6]}` | `signal_generator.py:249` |
| `decision_id` (Phase 9) | `dec_{compact_ts}_{symbol_lower}_{timeframe_lower}_{uuid4[:6]}` | `decision_logger.py:169` |
| `entry_id` (mémoire) | `mem-{uuid4[:12]}` ou `mem-{compact_ts}-{uuid4[:6]}` | `scene_builder.py`, `window_gate.py`, `exploitability_evaluator.py` |

**Écart vs convention idéale mentionnée initialement** (`v9-{SYMBOL}-{TF}-{timestamp}-{sequence}`,
`scene-{snapshot_id}`) : le code réel n'utilise ni le symbole/TF dans `snapshot_id`, ni le
`snapshot_id` complet comme suffixe de `scene_id`. Chaque couche génère son propre identifiant
horodaté + UUID court, et référence sa couche amont via une colonne `*_ref` séparée plutôt que
par construction de chaîne. **C'est la convention réelle à suivre pour tout nouveau code.**

## Branches Git

Convention observée et confirmée par l'historique (`git log`, `git branch -a`) :

| Type | Format | Exemples réels |
|---|---|---|
| Feature de phase | `feat/v9-phase{N}-{nom}` | `feat/v9-phase1-formats-aval`, `feat/v9-phase8-monitoring` |
| Branche de référence | `feat/v9-foundation-clean` | branche d'intégration de toutes les phases fusionnées |
| Correctif | `fix/v9-{description}` | `fix/v9-phase1-review` |
| Documentation | `docs/v9-{description}` | `docs/v9-governance` (cette branche) |
| Audit | `audit/{description}` | `audit/v8-to-v9-migration` |

## Voir aussi
- [docs/DOC_GOVERNANCE.md](DOC_GOVERNANCE.md) — règle : toute nouvelle table/module doit respecter cette nomenclature ou documenter l'écart ici
- [docs/architecture/DB_SCHEMA.md](architecture/DB_SCHEMA.md) — schéma complet
