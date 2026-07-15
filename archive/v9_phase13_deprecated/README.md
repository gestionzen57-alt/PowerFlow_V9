# Archive — Code V9 Phase 13 déprécié

Ces fichiers ont été archivés le 2026-07-15 lors de la consolidation du trade engine.

## Raison

Le module `core/v9/trade_engine.py` consolide désormais :
- `arbiter.py` → consolidation vote
- `risk_manager.py` + `paper_risk_manager.py` → gate go/no-go + sizing
- `exit_simulator.py` → SL/TP réels par session
- `paper_trade_logger.py` → ouverture/clôture DB
- `pyramiding_engine.py` → scaling descriptif

## Fichiers archivés

| Fichier | Raison |
|---|---|
| `v9_paper_trade_offline.py` | Supplanté par `trade_engine.run_batch()` |
| `v9_batch_resolve_dynamic.py` | Supplanté par `v9_batch_resolve_dynamic_full.py` |
| `v9_batch_resolve_tpsl.py` | Supplanté par DYNAMIC (exit_simulator) |
| `v9_resolve_decision.py` | Saisie manuelle, supplanté par `v9_resolve_decision_auto.py` |
| `execution_drift_analyzer.py` | DB_PATH cassé, non maintenu |
| `execution_threshold_audit.py` | DB_PATH cassé, non maintenu |

## Modules restaurés (dépendances de trade_engine)

| Fichier | Statut |
|---|---|
| `paper_risk_manager.py` | Actif — importé par trade_engine |
| `pyramiding_engine.py` | Actif — importé par trade_engine |