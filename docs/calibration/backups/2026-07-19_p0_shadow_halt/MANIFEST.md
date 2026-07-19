# Backup MD5 — 2026-07-19_p0_shadow_halt

**Date** : 2026-07-19 22:48 UTC
**Chantier** : P0 réouverture (motion CEO « go fait tout »)
**Motion CEO** : désactiver le shadow runtime, réparer les index UNIQUE
avec source_type, câbler V9_PAPER_TRADE_HALT dans TradeEngine.process(),
relancer le pipeline et revalider.

## Fichiers backupés (HEAD avant modif)

| Fichier | MD5 |
|---|---|
| core/v9/db_schema.py | `0f9d163191b695180982f9ef1e588ec3` |
| core/v9/principle_db.py | `a8b9d200b22caf474a5a323cb013613e` |
| core/v9/signal_db.py | `bea5e20535230bdd831a5811eea2d8f3` |
| core/v9/decision_db.py | `6d9230affc731c2d526f16bb768ac7d5` |
| core/v9/shadow_evaluator.py | `30bcb842ffb3344819a5ab05eed3c444` |
| core/v9/trade_engine.py | `7246f1e1179d5db64f681924bb52198d` |

## Modifications appliquées

### 1. Index UNIQUE incluant source_type
- `signals` : DROP `idx_signals_snapshot_id` + CREATE
  `idx_signals_snapshot_source_type (snapshot_id, source_type)`.
- `principle_evaluations` : DROP
  `idx_pe_snapshot_principle_currency` + CREATE
  `idx_pe_snapshot_principle_currency_source (snapshot_id, principle_id,
  currency, source_type)`.

### 2. Migration douce dans `init_signal_db` et `init_principle_db`
- DROP IF EXISTS de l'ancien index AVANT executescript() (sinon
  IntegrityError si la base contient déjà des doublons).
- DROP IF EXISTS défensif APRÈS executescript (re-créé par IF NOT
  EXISTS).
- `ensure_shadow_unique_index_*` : ROW_NUMBER partitionné, ligne live
  prioritaire, sinon id ASC. R6 fail-soft.

### 3. Câblage V9_PAPER_TRADE_HALT dans TradeEngine
- Import du kill switch helper `paper_trade_halt_enabled()`.
- Bloc en tête de `process()` (avant l'arbiter) qui retourne
  `action=skip` + `raison_blocage=paper_halt` sans appeler
  `paper_trade_logger.log_open()`.

### 4. Désactivation runtime V9_SHADOW_MODE_ENABLED
- `config/v9_kill_switches.env` : `1` → `0`.
- Le code et les tests du shadow sont conservés pour usage futur.

## Tests P0 livrés (RED → GREEN)

| Test | Fichier | Statut |
|---|---|---|
| `test_live_signal_not_overwritten_by_shadow` | tests/test_v9_p0_shadow_unique_index.py | RED → GREEN |
| `test_live_principle_evaluation_not_overwritten_by_shadow` | idem | RED → GREEN |
| `test_live_decision_not_overwritten_by_shadow` | idem | GREEN (déjà fixé) |
| `test_signals_unique_index_includes_source_type` | idem | RED → GREEN |
| `test_principle_evaluations_unique_index_includes_source_type` | idem | RED → GREEN |
| `test_paper_halt_kill_switch_defined` | tests/test_v9_p0_paper_halt.py | GREEN |
| `test_paper_halt_blocks_trade_engine_process` | idem | RED → GREEN |

7/7 tests P0 GREEN. 75/75 tests P0 + watchdog + kill_switch +
loop_breaker + shadow_evaluator verts.

## Doctrine respectée

- R6 (fail-safe)
- R7 (motion CEO explicite autorise la régression)
- R8 (ce backup MD5)
- R14 (Git = source de vérité)
- R18 (code pur, stdlib only)
- R22 (1 livraison = 1 commit)
- R25'' (kill switches OFF par défaut)
- R26 (tests RED puis GREEN, 0 régression)
- R28 (push après motion CEO)

## Référence

- workspace/perplexity/memory/DECISIONS_LOG.md §2026-07-19 22:48 UTC
- docs/security/PRE_REOUVERTURE_CHECKLIST_20260719.md
- commits <sha P0 livraison> + <sha P0 tests>
