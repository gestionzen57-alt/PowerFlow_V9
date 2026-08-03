# MCP Servers V9 — Architecture complète (Phase 12+)

> Snapshot 2026-08-03 06:30 UTC — sprint CEO no-stop 03/08

## Vue d'ensemble

Le projet V9 utilise **15 serveurs MCP** registered (1 helper stdio
interne non listé dans `.mcp.json`). Chaque serveur expose un sous-ensemble
d'outils spécialisés pour le bus agent et la chaîne cognitive.

## Tableau récapitulatif

| # | Serveur | Rôle | Outils exposés | Statut |
|---|---|---|---|---|
| 1 | `v9-doctrine` | Garde-fous doctrine (R6/R7/R14/R22/R25'/R28) | `check_doctrine_compliance`, `validate_commit_message` | ✅ |
| 2 | `v9-filesystem` | Lecture/écriture fichiers workspace | `read_file`, `write_file`, `list_directory`, `glob_files` | ✅ |
| 3 | `v9-meta-agent` | Orchestrateur agent Bus | `publish_event`, `poll_events`, `stats` | ✅ |
| 4 | `v9-p3-consume` | Consommation P3 adaptive thresholds | `consume_p3_threshold`, `check_active` | ✅ |
| 5 | `v9-pipeline` | Run/arrêt pipeline live | `run_pipeline`, `stop_pipeline`, `get_state` | ✅ |
| 6 | `v9-sqlite` | Accès DB v9_forces.db (lecture/écriture contrôlée) | `query`, `get_schema`, `get_table_info` | ✅ |
| 7 | `v9-strategy-pole` | Pôle stratégie data-driven V9 | `list_principles`, `get_strategy_profile`, `evaluate_signal` | ✅ |
| 8 | `v9-telegram` | Notifications Telegram (motion CEO requise) | `send_message`, `send_alert` | ⚠️ Tokens cassés (A1) |
| 9 | `v9-paper-trade` | Paper trade execution (Phase 12 FTMO ACTIVE) | `open_paper_trade`, `close_paper_trade`, `get_open_trades` | ✅ |
| 10 | `v9-meta-strategy-shadow` | Méta-strategy shadow (observation) | `evaluate_meta_strategy`, `get_shadow_state` | ✅ |
| 11 | `v9-data-integrity` | Audit DB source (R7/R8) | `quick_check`, `integrity_check`, `freeeze_test` | ✅ |
| 12 | `v9-edge-decay` | Surveillance dégradation edge | `check_edge_decay`, `propose_demotion` | ✅ |
| 13 | `v9-risk-dashboard` | Dashboard risk live (DD, WR, CVaR) | `get_risk_metrics`, `get_dd_state` | ✅ |
| 14 | `v9-meta-agent-bus` | Bus agent inter-IA (ZCode, Hermes, Claude CLI) | `publish`, `poll`, `stats`, `pending` | ✅ |
| 15 | `v9-walk-forward` | Walk-forward validation | `run_walk_forward`, `get_validation_report` | ✅ |

## Helper stdio (non registered)

- `mcp_servers/stdio_runtime.py` : runtime stdio pour serveur CLI (helper
  interne, lancé en sous-process par les autres serveurs).

## Configuration

`config/mcp_config.json` (si présent) ou `.mcp.json` à la racine du projet.
Recharger après modif : redémarrer la session Hermes.

## Doctrine

- R6 fail-open : serveurs MCP ne doivent JAMAIS lever d'exception non
  capturée (kill switch par défaut OFF).
- R18 zero LLM : aucun serveur MCP n'utilise de LLM dans le cœur.
- R22 sous-unite : chaque serveur = 1 responsabilité claire.
- R25' motion CEO : activation du Telegram motion CEO explicite.
- R28 Hermes git unique : modifications du registre MCP via Hermes.

## Évolution récente (sprint CEO 03/08)

- 16 serveurs total (1 helper + 15 registered)
- 12 outils exposés utiles pour le sprint CEO 03/08
- v9-telegram partiellement down (rotation tokens CEO A1 motion requise)