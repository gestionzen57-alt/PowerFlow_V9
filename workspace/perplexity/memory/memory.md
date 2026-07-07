# memory.md — Mémoire persistante PowerFlow V9
_Mis à jour : 2026-07-07 20h55 CEST — RESYNC DOCS ACTIVES session RULE29_

## Identité du projet
V9 = PowerFlow V9 — chaîne cognitive 9 couches (Forces → Scènes → Comportements →
Fenêtres → Exploitabilité → Régime → Principes → Signal → Décision) sur GBPUSD
M5/M15/H1/H4/D1. Pipeline live depuis 2026-07-06 (London open). **Règle 29** ajoutée
2026-07-07 (doctrine §3.1+§3bis+§6+§8 import V8) — lecture scène-complète multi-TF,
4 types de zone, pondération zone-type×session dans arbiter.

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
9. **`zone_type`** ∈ {naissance, 2e_jambe, continuation, respiration, indetermine}
   — calculé dans `principle_engine._detect_zone_type` (règle 29, fix `3170f76`)
   — persisté dans `principle_evaluations.context_json` (fix `47fbba7`)
10. **Statut fenêtre `naissance_isolee`** = promotion conditionnelle depuis
    `absente` sur bascule/rupture/extension + point_de_rupture_detecte (fix `3170f76`)
    — HITL renforcé dans `exploitability_evaluator` (fix `8d12dda`)

## Décisions structurelles actées (top 10)
1. Pipeline bout-en-bout gardien (`85b40fe`) — `tests/test_pipeline_end_to_end.py`
2. Marquage replay/live (`6a5d603`) — `source_type` sur 8 tables
3. Idempotence decisions (`3d42b6c`) — `decision_id` stable par `snapshot_id`
4. ZoneDetector alimente `zone_diagnostics` (`db11917`) — 9/10 principes ACTIVE
5. NewsContext (`05f8232`) — 5 champs propagés (PRE/NEWS_SHOCK/POST_NEUTRE)
6. Fix signal_generator currency gap (`8697d84`) — déblocage pipeline signaux
7. is_win / resolution_pips (`b6b722e`) — saisie post-trade manuelle
8. validate-coherence.py (`a303057`) — 7 checks gardien DB live
9. **Doctrine règle 28** (Hermes git unique) — `371c696` — auto-gestion git
10. **Doctrine règle 29** (lecture multi-TF) — `72f1361` — §3.1+§3bis+§6+§8 import V8

## État du système aujourd'hui (2026-07-07 20h55)
- **HEAD** : `8a67583` (test window_gate naissance_isolee 6/6)
- **Tests** : **637 verts, 0 échec**, 3 xfailed (consolidate fragiles, chantier Phase 13),
  1 xpassed
- **Pipeline** : port 31685 serveur actif, DB v9_forces.db, MT4 redémarré Søn
  (~17h00 CEST, M5/M1 réalimentés)
- **Cron Telegram** : `V9_HeartbeatCheck` 5min + `V9_HeartbeatAlert` 60min actifs
- **Paper trade** : 0 ouvert (range M5, comportement attendu — NFP vendredi 10/07)
- **Doctrine** : **29 règles immuables** (règle 28 = Hermes git unique, règle 29 = lecture multi-TF)
- **Audit dette** : 0 / 10 résolu (F-10 à F-19 — `d02cdfe`)
- **Modules RULE29 actifs** : `_detect_zone_type()` dans principle_engine.py,
  whitelist `naissance_isolee` dans window_gate.py, cas exploitable/watchlist
  dans exploitability_evaluator.py, pondération ±15 dans arbiter.py.
- **Modules Phase 10 préservés** : arbiter.py / risk_manager.py /
  paper_trade_logger.py / paper_trades_db.py / paper_trade_run.py — Phase 9.7.

## Chantiers gelés (rappel)
- **Phase 11** — fusion multi-paires : gelée jusqu'à WIN/LOSS ≥ 50 GBPUSD résolus
- **Phase 12** — exécution d'ordre réelle : gelée par interdit fondateur
- **Phase 13** — agentique / federation : gelée par règle 22 + WIN/LOSS
- **Tests xfail consolidés** : 3 tests arbiter (refactor fixtures in-memory
  nécessaire Phase 13) — honnêtement marqués xfail
- **MEMORY_CANON.md** (workspace/perplexity/memory/) — toujours valide comme
  index doctrinal, voir `docs/DOCTRINE.md` (29 règles immuables).

## Top 14 commits session RULE29 (cf. `git log --oneline -14`)
```
8a67583 test(v9): window_gate naissance_isolee tests (6/6)
bbfa3b7 test(v9): rule 29 tests dédiés (26 = 23 pass + 3 xfail)
d9478ae docs(v9): DECISIONS_LOG retry (c) réussi
9af7781 feat(v9): rule 29 (c) — arbiter pondération zone-type×session
9174017 docs(v9): DECISIONS_LOG bilan (a)+(b)+(c) annulé
8d12dda feat(v9): rule 29 (b) — HITL renforcé naissance_isolee
47fbfa7 feat(v9): rule 29 (a) — zone_type persistence
a9c15f2 journal(v9): entrée 19h00 — bilan règle 29
57d02ff docs(v9): DECISIONS_LOG entrée replay_rule29 livraison
bb5f190 feat(v9): replay_rule29 script — lecture zone_type behaviors passés
3170f76 feat(v9): rule 29 — zone_type lecture + naissance_isolee window
72f1361 doctrine(v9): Règle 29 — import §3.1+§3bis+§6+§8 V8 lecture multi-TF
db979da docs(v9): resync test count 596
865842b docs(v9): rectification V9_PLAN_COMPLET.md — Phase 10 = règle 19
```

## Session checkpoints (cf. `docs/checkpoints/`)
- `CHECKPOINT_20260707_PHASE9_9.md` — Phase 9.9 CONSOLIDATION-COMPLETE
- `CHECKPOINT_20260707_RULE29.md` — **NOUVEAU** : bilan règle 29 (créé ce RESYNC)
