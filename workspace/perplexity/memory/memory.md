# memory.md — Mémoire persistante PowerFlow V9
_Mis à jour : 2026-07-07 10h08 CEST_

## Identité du projet
V9 = PowerFlow V9 — chaîne cognitive 9 couches (Forces → Scènes → Comportements →
Fenêtres → Exploitabilité → Régime → Principes → Signal → Décision) sur GBPUSD
M5/M15/H1/H4/D1. Pipeline live depuis 2026-07-06 (London open), 7 signaux
directionnels GBPUSD baissiers produits 2026-07-07 (conf 80-100).

## Conventions immuables
1. `snapshot_id` = `v9-{SYMBOL}-{TF}-{bar_time}-{seq}` (déterminé par MT4/EA)
2. `source_type` ∈ {`live`, `replay`} — colonne portée par les 8 tables dérivées
   (scenes, behaviors, windows, exploitability, regime_snapshots,
   principle_evaluations, signals, decisions) — règle 12 doctrine
3. `currency` = devise de base pour signal (`GBP` pour GBPUSD) — fix `8697d84`
4. **HITL requise** avant tout ordre réel (rappel : aucune logique d'exécution
   d'ordre avant Phase 12, interdit fondateur)
5. `decision_id` = `dec_` + uuid5(snapshot_id).hex[:12] — idempotent par
   snapshot_id (fix `3d42b6c`)
6. Migration DB toujours **idempotente** (pattern `_ensure_column` de
   `core/v9/db_schema.py`) — pas de touche live DB
7. `principes_json` = JSON array, ordre stable par 1ère apparition (cf. Arbiter)
8. `is_win` ∈ {0, 1, NULL} — convention NULL = non résolu (cf. `b6b722e`)

## Décisions structurelles actées
1. Pipeline bout-en-bout gardien (`85b40fe`) — `tests/test_pipeline_end_to_end.py`
2. Marquage replay/live (`6a5d603`) — `source_type` sur 8 tables
3. Idempotence decisions (`3d42b6c`) — `decision_id` stable par `snapshot_id`
4. ZoneDetector alimente `zone_diagnostics` (`db11917`) — 9/10 principes ACTIVE
5. NewsContext (`05f8232`) — 5 champs propagés (PRE/NEWS_SHOCK/POST_NEUTRE)
6. Fix signal_generator currency gap (`8697d84`) — déblocage pipeline signaux
7. is_win / resolution_pips (`b6b722e`) — saisie post-trade manuelle
8. validate-coherence.py (`a303057`) — 7 checks gardien DB live

## État du système aujourd'hui
- **HEAD** : `9e3c351` (était `a303057` avant push session 2026-07-07)
- **Tests** : **426 verts, 0 échec** (était 359 au checkpoint Phase 9 2026-07-05)
- **Modules Phase 10 actifs** : `core/v9/arbiter.py` (consolidation),
  `core/v9/risk_manager.py` (filtre), `core/v9/paper_trade_logger.py` (saisie),
  `core/v9/paper_trades_db.py` (table). SHA : `134205e` / `71007d7` / `83b6098`.
- **Cron Telegram** : script `scripts/v9_telegram_notifier.py` opérationnel
  (mode `--watch`), **pas de cronjob persistant enregistré** — en attente
  session dédiée.
- **Gaps connus** : GAP-001 (7 décisions orphelines — archivé non bloquant),
  Check 4 stale (historique J-1 normal), WIN/LOSS = 0 (collecte via
  `scripts/v9_resolve_decision.py`).
- **Doc pivot** : `docs/checkpoints/CHECKPOINT_20260707_PHASE9_TO_PHASE10.md`
  (transition Phase 9 → Phase 10 actée 2026-07-07).

## Chantiers gelés
- **Phase 11** — fusion multi-paires (EURUSD, USDJPY...) : gelée jusqu'à
  WIN/LOSS ≥ 50 GBPUSD résolus.
- **Phase 12** — exécution d'ordre réelle : gelée par interdit fondateur
  (doctrine Phase 9 — règle HITL avant ordre).
- **Phase 13** — agentique globale / federation multi-providers : gelée
  par règle 22 doctrine (architecture agents/skills gelée tant que la
  phase métier courante n'est pas canonisée et stable).
- **MEMORY_CANON.md** (workspace/perplexity/memory/) — toujours valide
  comme index doctrinal, voir `docs/DOCTRINE.md` (27 règles immuables).