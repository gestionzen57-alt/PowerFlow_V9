# CHECKPOINT — Marquage replay/live (colonne `source_type`)

## Date
2026-07-06

## Contexte
Point ouvert depuis Phase 7-8 (doctrine règle 12) : les décisions produites par la chaîne
cognitive V9 ne portaient aucun marquage permettant de distinguer une décision produite sur
des données live (capture temps réel) d'une décision produite sur des données replay
(régénération via `regenerate_chain.py`).

## Changement appliqué
Ajout de la colonne `source_type TEXT` ("live"/"replay") aux 8 tables dérivées :

| Table | Fichier schéma |
|---|---|
| `scenes` | `core/v9/scene_db.py` |
| `behaviors` | `core/v9/behavior_db.py` |
| `windows` | `core/v9/window_db.py` |
| `exploitability` | `core/v9/exploitability_db.py` |
| `regime_snapshots` | `core/v9/regime_db.py` |
| `principle_evaluations` | `core/v9/principle_db.py` |
| `signals` | `core/v9/signal_db.py` |
| `decisions` | `core/v9/decision_db.py` |

### Propagation
- `orchestrator.run_chain()` accepte un paramètre `source_type` (défaut `"live"`).
- Chaque constructeur de couche reçoit `source_type` via son `config` dict ou paramètre direct.
- Chaque méthode `_write_*_to_db()` insère `self.source_type` dans la colonne.
- `regenerate_chain.py` passe `source_type="replay"` à `run_chain()`.
- `capture_server.py` appelle `run_chain()` sans argument → `"live"` par défaut.

### Rétrocompatibilité
- Les 1290 décisions existantes (replay) restent avec `source_type = NULL`.
- Aucune modification de `core/v9/config.py`, de la logique métier, ni des tests existants.
- `CREATE TABLE IF NOT EXISTS` garantit que les bases existantes ne sont pas recréées.

## Fichiers modifiés
- `core/v9/orchestrator.py` — paramètre `source_type` + propagation
- `core/v9/scene_builder.py` — `source_type` dans config + écriture DB
- `core/v9/behavior_analyzer.py` — `source_type` dans config + écriture DB
- `core/v9/window_gate.py` — paramètre `source_type` + écriture DB
- `core/v9/exploitability_evaluator.py` — `source_type` dans config + écriture DB
- `core/v9/regime_detector.py` — paramètre `source_type` + écriture DB
- `core/v9/principle_engine.py` — paramètre `source_type` + écriture DB
- `core/v9/signal_generator.py` — paramètre `source_type` + écriture DB
- `core/v9/decision_logger.py` — paramètre `source_type` + écriture DB
- `core/v9/scene_db.py` — colonne `source_type` dans schéma + `SCENES_COLUMNS`
- `core/v9/behavior_db.py` — colonne `source_type` dans schéma + `BEHAVIOR_COLUMNS`
- `core/v9/window_db.py` — colonne `source_type` dans schéma + `WINDOWS_COLUMNS`
- `core/v9/exploitability_db.py` — colonne `source_type` dans schéma + `EXPLOITABILITY_COLUMNS`
- `core/v9/regime_db.py` — colonne `source_type` dans schéma + `REGIME_SNAPSHOTS_COLUMNS`
- `core/v9/principle_db.py` — colonne `source_type` dans schéma + `PRINCIPLE_EVALUATIONS_COLUMNS`
- `core/v9/signal_db.py` — colonne `source_type` dans schéma + `SIGNALS_COLUMNS`
- `core/v9/decision_db.py` — colonne `source_type` dans schéma + `DECISIONS_COLUMNS`
- `scripts/regenerate_chain.py` — passage de `source_type="replay"`
- `docs/DOCTRINE.md` — règle 12 marquée résolue
- `docs/ROADMAP.md` — point ouvert marqué résolu
- `docs/phases/PHASE9_DECISION.md` — écart marqué résolu
- `workspace/perplexity/BOARD.md` — blocage mis à jour
- `workspace/perplexity/memory/DECISIONS_LOG.md` — entrée ajoutée

## Tests
- Aucun test existant modifié (rétrocompatibilité).
- Les tests existants continuent de passer : les constructeurs sans `source_type` reçoivent `"live"` par défaut.
