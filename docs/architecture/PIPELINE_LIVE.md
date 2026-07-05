# PIPELINE LIVE — PowerFlow V9

## Statut
Flux bout en bout EA → TCP → Python → DB → chaîne cognitive, vérifié contre le code réel
le 2026-07-05. Pour le détail de chaque couche cognitive, voir
[CHAINE_COGNITIVE.md](CHAINE_COGNITIVE.md). Pour le schéma DB, voir [DB_SCHEMA.md](DB_SCHEMA.md).
Pour la procédure de déploiement, voir
[docs/deployment/V9_DEPLOYMENT_GUIDE.md](../deployment/V9_DEPLOYMENT_GUIDE.md).

## 1. Capture (MT4 → EA)

- **MT4 + indicateur SDI** (propriétaire) calcule les forces de 8 devises sur 7 timeframes.
- **`ea/V9_Sonde_TF.mq4`** : une instance par timeframe candle-close (M5/M15/M30/H1/H4/D1),
  déclenchée en `OnTimer`, lit `Period()` réel (jamais hardcodé — bug V8 corrigé par
  construction). Input `ServerPort` (défaut 31685, configurable — avant Phase 7 c'était une
  constante Winsock figée). Input `BrokerUTCOffsetHours` pour la conversion temporelle.
- **`ea/V9_Sonde_M1.mq4`** : instance M1 dédiée, mode tick/vélocité (`OnTick`, pas de timer),
  fenêtre glissante de 5s (`VelocityWindowMs`), anti-duplicate (`MinForceDelta`).
- Formatage JSON conforme à `docs/architecture/formats/FORMAT_FORCES.md`, envoi TCP vers le
  serveur de capture.

## 2. Réception (`core/v9/capture_server.py`)

- Serveur asyncio, écoute `LISTEN_HOST:LISTEN_PORT` (127.0.0.1:31685 par défaut,
  configurable dans `config.py`).
- `handle_client` : 1 message EA = 1 connexion TCP.
- Transformation via `ForcesReader.transform()` puis `to_snapshot()`.
- `StaleGate.check_freshness()` : calcule l'âge de la donnée, la marque `stale=True` si elle
  dépasse le seuil du timeframe (`STALE_THRESHOLDS_MS` dans `config.py`) — **ne rejette
  jamais l'insertion**, marque seulement.
- `insert_row` : `INSERT OR IGNORE` dans `forces_snapshots`, protégé par l'index
  `idx_unique_closed_bar` (anti-replay, voir [DB_SCHEMA.md](DB_SCHEMA.md)).
- Si l'insertion a réussi **et** la donnée n'est pas stale **et** `config.ENABLE_CHAIN` est
  vrai : appel de `orchestrator.run_chain(snapshot_id)`.
- CLI : `--once` (traite un message puis quitte), `--status` (compteurs par couche/TF).

## 3. Orchestration (`core/v9/orchestrator.py`)

`run_chain(snapshot_id)` exécute séquentiellement :

1. `SceneBuilder.build_scene` → `scenes`
2. `BehaviorAnalyzer.analyze_scene` → `behaviors`
3. `WindowGate.evaluate_behavior` → `windows`
4. `ExploitabilityEvaluator.evaluate_window` → `exploitability`
5. *(Phase 9, en cours)* `RegimeDetector.detect` → `regime_snapshots`
6. *(Phase 9, en cours)* `PrincipleEngine.evaluate_principles` → `principle_evaluations`
7. *(Phase 9, en cours)* `SignalGenerator.generate` → `signals`
8. *(Phase 9, en cours)* `DecisionLogger.log` → `decisions`

**Chaque étape est isolée dans son propre `try/except`** : une erreur sur une couche arrête
la chaîne à cette étape (`result["error"] = <nom_couche>`) sans jamais remonter d'exception
à `capture_server.py` (doctrine règle 6 — l'orchestrateur ne crash jamais).

## 4. Stockage

Une seule base SQLite, `data/v9_forces.db`, mode WAL, `busy_timeout=30000`. Toutes les
tables et leurs colonnes exactes : [DB_SCHEMA.md](DB_SCHEMA.md).

## 5. Observation (lecture seule stricte)

- `scripts/v9_dashboard.py` — dashboard terminal temps réel (`--interval N`, `--once`,
  `--watch comportements|fenetres`).
- `scripts/v9_calibration.py` — `--stats`, `--export csv|json`, `--analyze` (suggestions de
  seuils, jamais appliquées automatiquement).
- `scripts/v9_replay.py` — `--list`, `--show <id>`, `--compare <id1> <id2>`, `--search`.
- Aucun de ces trois scripts n'écrit dans `data/v9_forces.db` ni ne modifie `config.py`.

## 6. Cycle de vie du serveur (`scripts/deploy_v9.py`)

- `--check` : Python 3.11+, modules `core/v9/` importables, DB + tables présentes, port
  disponible, vérification souple de connexion EA.
- `--start` : lance `capture_server.py` en sous-processus, PID file `logs/v9_capture.pid`.
- `--status` : compteurs par couche et par timeframe, taux de stale, âge du dernier snapshot.
- `--stop` : arrêt via PID file (`taskkill` sur Windows).

## 7. Validation et test d'intégration

- `scripts/validate_ea_output.py` : reçoit 1 message EA, valide sa conformité à
  `FORMAT_FORCES.md`, vérifie la cohérence du timestamp UTC déclaré vs `capture_time`
  broker reconverti, heuristique de plausibilité AUD (doit se situer entre EUR et NZD).
- `scripts/live_integration_test.py` : copie les nouveaux snapshots non-stale de la DB de
  production vers une DB de test dédiée (`data/v9_live_test.db`), fait traverser la chaîne
  complète sur cette copie, mesure le temps par couche. **Ne modifie jamais la DB de
  production.**
- `scripts/regenerate_chain.py` : rejoue `orchestrator.run_chain` sur tous les snapshots
  non-stale existants dans l'ordre chronologique — utilisé après un correctif touchant la
  chaîne (ex. bug de non-idempotence du replay corrigé en Phase 9).

## Référentiel temporel (`core/v9/market_calendar.py`)

`MarketCalendar` (méthodes statiques, aucune I/O) : `is_market_open`, `current_session`
(sydney/tokyo/london/new_york/overlap_london_ny/closed, priorité overlap > london >
new_york > tokyo > sydney en cas de chevauchement), `next_open`, `broker_to_utc`/
`utc_to_broker` (offset fixe GMT+3, broker Tickmill/FTMO), `paris_to_utc` (DST via
`zoneinfo`, sans dépendance externe).

## Performance mesurée
~148 ms par snapshot pour la traversée complète de la chaîne Forces→Exploitabilité
(mesure Phases 1-8, avant l'ajout des couches Phase 9 — voir
[docs/v9_processus_complet.md](../v9_processus_complet.md) §4).
