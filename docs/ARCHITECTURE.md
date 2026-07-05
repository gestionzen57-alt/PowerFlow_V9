# ARCHITECTURE — PowerFlow V9

## Statut
Vue d'ensemble technique. Pour le détail on va vers les documents spécialisés :
[CHAINE_COGNITIVE.md](architecture/CHAINE_COGNITIVE.md) (les 5+1 couches),
[DB_SCHEMA.md](architecture/DB_SCHEMA.md) (schéma SQLite complet),
[PIPELINE_LIVE.md](architecture/PIPELINE_LIVE.md) (flux EA → TCP → Python → DB),
[docs/architecture/formats/](architecture/formats/) (formats JSON par couche).
**Vérifié contre le code réel le 2026-07-05** (branche `feat/v9-foundation-clean`,
commit `78d2621`, plus code Phase 9 — vérifié à nouveau le 2026-07-05 à la clôture
documentaire de la Phase 9 : `python -m pytest tests/ -q` → 214 tests, tous verts).

## Vue d'ensemble

PowerFlow V9 lit les forces relatives de 8 devises sur 7 timeframes, les structure en
scènes, qualifie leur dynamique en comportements, détecte des fenêtres d'opportunité, et
juge tardivement leur exploitabilité — avant toute décision ou exécution. Voir
[docs/DOCTRINE.md](DOCTRINE.md) et [docs/LEXIQUE.md](LEXIQUE.md) pour la doctrine et le
vocabulaire complets.

## Flux de données (vue haut niveau)

```
MT4 + indicateur SDI (propriétaire)
    │  lecture des buffers (8 devises × 7 TF)
    ▼
EA V9_Sonde_TF.mq4 (candle-close, 1 instance/TF) + V9_Sonde_M1.mq4 (tick/vélocité)
    │  formatage JSON (FORMAT_FORCES.md) + envoi TCP
    ▼
capture_server.py (asyncio, port LISTEN_PORT=31685)
    │  stale_gate.py (marque stale si âge > seuil par TF, jamais de suppression)
    │  anti-replay : INSERT OR IGNORE + UNIQUE INDEX (symbol, timeframe, bar_time)
    ▼
data/v9_forces.db → table forces_snapshots
    │  orchestrator.run_chain(snapshot_id) — déclenché si non-stale et config.ENABLE_CHAIN
    ▼
    CHAÎNE COGNITIVE (try/except indépendant par étape, jamais de crash propagé)
    1. SceneBuilder          → table scenes
    2. BehaviorAnalyzer      → table behaviors
    3. WindowGate            → table windows
    4. ExploitabilityEvaluator → table exploitability
    5. RegimeDetector        → table regime_snapshots
    6. PrincipleEngine       → tables principles / principle_evaluations
    7. SignalGenerator       → table signals
    8. DecisionLogger        → table decisions
```

Voir [docs/PIPELINE_LIVE.md](architecture/PIPELINE_LIVE.md) pour le détail pas-à-pas et
[CHAINE_COGNITIVE.md](architecture/CHAINE_COGNITIVE.md) pour le rôle de chaque couche.

## Ordre cognitif officiel (5+1, doctrine)

1. Forces — 100% des données brutes, aucun filtre
2. Scènes — structure l'information (qui/quoi)
3. Comportements — ajoute la dynamique (comment)
4. Fenêtres — filtre par opportunité (quand)
5. Exploitabilité — filtre par qualité (est-ce tradable)
6. Décision (Phase 9) — transforme en action recommandée, jamais un ordre direct

Aucune couche aval ne peut court-circuiter une couche amont
([DOCTRINE.md](DOCTRINE.md), [CHARTE_COGNITIVE_V9.md](doctrine/CHARTE_COGNITIVE_V9.md)).

## Modules `core/v9/` — stables (Phases 1-9)

| Module | Rôle |
|---|---|
| `config.py` | Configuration centrale : chemins, ports, devises/timeframes, seuils STALE_GATE, calibration par couche, référentiel temporel marché |
| `market_calendar.py` | `MarketCalendar` — ouverture/session/conversions temporelles (broker↔UTC↔Paris), aucune I/O |
| `stale_gate.py` | `StaleGate` — fraîcheur des données par timeframe, marque stale sans jamais supprimer |
| `forces_reader.py` | `ForcesReader` — transforme le JSON brut EA en format V9 (direction, vitesse, croisement, recroisement, rejet/répulsion, compression/extension) |
| `capture_server.py` | Serveur TCP asyncio (port `LISTEN_PORT`) : réception EA, insertion `forces_snapshots`, déclenchement orchestrateur |
| `db_schema.py` | Schéma SQLite `forces_snapshots` (WAL, busy_timeout 30s), index anti-replay |
| `scene_builder.py` | `SceneBuilder` — coalitions, antagonismes, cinématique locale, confluences MTF, contexte temporel, zone |
| `scene_db.py` | Schéma SQLite `scenes` (référence `forces_snapshot_ref`, jamais de duplication) |
| `behavior_analyzer.py` | `BehaviorAnalyzer` — qualification de dynamique (12 types), transitions, comparaison aux cas connus |
| `behavior_db.py` | Schéma SQLite `behaviors` (référence `scene_id_ref`) |
| `window_gate.py` | `WindowGate` — statut de fenêtre (6 valeurs), type, fragilité, cycle de vie |
| `window_db.py` | Schéma SQLite `windows` (référence `behavior_id`) |
| `exploitability_evaluator.py` | `ExploitabilityEvaluator` — statut d'exploitabilité (5 valeurs), raison de refus, confiance globale, HITL, replay_context |
| `exploitability_db.py` | Schéma SQLite `exploitability` (référence `window_id`) |
| `orchestrator.py` | `run_chain(snapshot_id)` — enchaîne les 8 couches Forces→Décision, chaque étape isolée par try/except (doctrine règle 6) |
| `regime_db.py` / `regime_detector.py` | `RegimeDetector` — machine à états portée de V8, régimes NEUTRE/PALIER/CASSURE/EXTENSION/RETOUR_EQUILIBRE/REJET sur fenêtre glissante (Phase 9) |
| `principle_db.py` / `principle_engine.py` | `PrincipleEngine` — évalue les principes YAML (`core/v9/principles/`), 10 principes ACTIVE routés, 17 en mode SHADOW (journalisés, non routés) (Phase 9) |
| `signal_db.py` / `signal_generator.py` | `SignalGenerator` — agrège les principes ACTIVE déclenchés en direction + confiance, filtré par exploitabilité et régime (Phase 9) |
| `decision_db.py` / `decision_logger.py` | `DecisionLogger` — action recommandée qualitative (observer/surveiller/preparer_entree/aucune_action), jamais un ordre (Phase 9) |
| `zone_db.py` | Schéma `zone_diagnostics` — table créée, **non encore alimentée** par un détecteur (gap connu, voir [PHASE9_DECISION.md](phases/PHASE9_DECISION.md)) |
| `core/v9/principles/*.yaml` | 27 définitions de principes (9 `node_rule` + 18 `GRAMMAR_*`), portés de V8 tels quels après audit (Phase 9) |

## Scripts `scripts/`

| Script | Rôle |
|---|---|
| `deploy_v9.py` | `--check` / `--start` / `--status` / `--stop` — cycle de vie du serveur de capture |
| `validate_ea_output.py` | Valide la conformité d'un message EA à `FORMAT_FORCES.md` |
| `live_integration_test.py` | Fait traverser la chaîne complète sur une copie de données live, DB de test dédiée, jamais d'écriture en production |
| `v9_dashboard.py` | Dashboard terminal temps réel, lecture seule strict |
| `v9_calibration.py` | Stats / export / suggestions de seuils, lecture seule, ne modifie jamais `config.py` |
| `v9_replay.py` | Liste / affiche / compare / recherche des comportements passés, lecture seule |
| `regenerate_chain.py` | Rejoue `orchestrator.run_chain` sur tous les snapshots non-stale existants ; `--replace-derived`/`--dry-run`, refuse par défaut si la DB dérivée n'est pas vide (anti-doublon) |

## Dépendances externes

- **MT4** avec indicateur SDI propriétaire (source unique des forces, pas de fallback identifié)
- **Python 3.11+** (stdlib uniquement pour les couches cognitives ; pas de `rich`/`colorama`)
- **SQLite** (`data/v9_forces.db`, mode WAL, `busy_timeout` 30s) — pas de serveur DB externe
- **MT5** (Phase 11, pas encore implémenté) — confirmera les forces MT4 via microstructure ticks
- **Aucun provider ou modèle LLM** dans la chaîne cognitive critique (Forces→Décision, Phases
  1-9) — les 27 principes sont des grammaires YAML déterministes, `PrincipleEngine`/
  `SignalGenerator`/`DecisionLogger` ne font aucun appel réseau ni inférence externe. Voir
  [DOCTRINE.md](DOCTRINE.md) règle 18. Une éventuelle fédération d'agents LLM (Phase 10) reste
  un chantier séparé, en aval de cette chaîne, jamais une dépendance de celle-ci.

## Voir aussi

- [docs/DOCTRINE.md](DOCTRINE.md) — règles immuables
- [docs/LEXIQUE.md](LEXIQUE.md) — vocabulaire métier
- [docs/NOMENCLATURE.md](NOMENCLATURE.md) — conventions de nommage
- [docs/ROADMAP.md](ROADMAP.md) — phases 9-13
- [docs/STATE.md](STATE.md) — état exécutif courant
