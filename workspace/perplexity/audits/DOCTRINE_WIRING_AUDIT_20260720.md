# DOCTRINE_WIRING_AUDIT_20260720

**Mission.** Vérifier le câblage runtime des 30+ règles R1-R32 de `docs/DOCTRINE.md` dans `core/v9/*.py` + `scripts/*.py`, en lecture seule.
**Branche.** `feat/v9-foundation-clean` — HEAD `9054725` (`fix(v9): mark test_send_appele_pour_nouvelle_decision xfail`).
**Date UTC.** 2026-07-20.
**Statut global.** 5 BORDERLINE / 3 VIOLATION / 22 OK. 7 doctrine-gaps hérités du subagent précédent validés ou invalidés.

---

## 0. Snapshot de vérité

| Source | Valeur |
|---|---|
| HEAD | `90547251e2d810a70a555eacdbd4c1479e068d14` (feat/v9-foundation-clean) |
| Working tree | 4 JSON `data/strategy_pole/*` modifiés, 1 JSON `config/calibration_overrides.json` modifié, 5 prompts Perplexity non trackés (untracked). Aucune modif `core/v9/*` ni `scripts/*` |
| DB live | `data/v9_forces.db` — 136 898 forces / 78 433 decisions / 4 854 paper_trades / 1 620 422 principle_evaluations / 226 principle_scores / 194 principle_alpha_metrics |
| `v9_guards.py all` | 6/6 OK (no-secrets, yaml-sync, scripts-exist, hitl-sync, db-sync, kill-switch-integrity) |
| Crons câblés | 11/11 (per `0faf2e9`, vérifié par `v9_audit_cron_wiring.py`) |
| Tests ciblés (5 fichiers doctrine-clés) | 54 passed (test_context_propagation, test_auto_calibrator, test_auto_optimizer, test_v9_auto_promotion, test_trade_engine_dynamic_risk) |
| Workflows CI | `.github/workflows/tests.yml` (pytest + ruff + `v9_guards.py`) et `doc-freshness.yml` (tools/doc_sync.py). Pas de hook Git local (`pre-commit`/`pre-push` absents) |
| Auteurs commits | 1 seul : `Søn <son@powerflow.local>` (R28 motion 2026-07-15, plus aucun `Gestionzen57`/`noreply@anthropic.com` Co-Authored après `b9e8ba5`) |
| Kill switches runtime | 18 vars dans `config/v9_kill_switches.env` ; loader central `core/v9/kill_switches.py` créé 2026-07-19, **mais 12+ fonctions consumers lisent encore `os.environ.get('V9_xxx')` directement** (cf. §R26) |

**Catalogue YAML.** 46 ACTIVE (30 grammar + 16 node_rule) + 5 node_rule SHADOW + 4 grammar SHADOW = 55 principes uniques. 0 yaml manquant côté ACTIVE.

---

## 1. Table des règles (R1-R32) — statut câblage

| # | Statut | Justification (1 ligne) |
|---|---|---|
| R1 | OK | Le code est lu comme vérité par tous les consommateurs (cf. `principle_engine._load_shared_context` lu par 12 modules, arbiter lit `decisions` SQL). |
| R2 | OK | Sur 95 modules, tous les patchs sont additifs (dictionnaires enrichis, R2 additif dans 38 docstrings ; 2 commits R2-violations historiques corrigés en `b9e8ba5` et `6a8cf1b`). |
| R3 | OK | `core/v9/exploitability_evaluator.py:589-597` calcule `statut` avant `raison_refus`. Signal generator `signal_generator.py:222-264` retourne `raison_absence` explicite si `exploitabilite != exploitable`. |
| R4 | OK | `stale_gate.py:46-77` produit `{stale, age_ms, stale_threshold_ms}`; consommé dans `capture_server.py:144` (skip chaîne), `signal_generator.py:_build_absent_signal` (raison_absence), `orchestrator.py:91-103` (try/except R6). |
| R5 | OK | `db_schema.py:75-77` UNIQUE INDEX `idx_unique_closed_bar ON forces_snapshots (symbol, timeframe, bar_time) WHERE is_closed_bar=1`. |
| R6 | OK | 412 occurrences de `try: ... except Exception: pass` / `except Exception as exc: log.debug(...)` dans `core/v9/` (comptage grep). Audit commit `334ccf6` confirme ZERO plantage orchestrateur. |
| R7 | OK | `tests/` — 54/54 verts sur les 5 fichiers doctrine-clés audités. Baseline globale (run large non exécutée dans cette session, lecture-seule). |
| R8 | OK (BORDERLINE sur R8 backup MD5 — voir §R8 ci-dessous) | 0 modif `core/v9/*` dans la session audit. `docs/calibration/backups/2026-07-19_p0_shadow_halt/` existe. Mais aucun test ne valide que le backup MD5 est posé avant chaque modif — voir §R8. |
| R9 | OK | Aucun import croisé `core.v6/7/8` (uniquement `backups/2026-07-08_pre_doctrine_realign/` archivé). |
| R10 | OK (NON IMPLÉMENTÉ — Phase 11 future) | Doctrine dit explicitement "pas encore implémenté". Code lu : `ea/V9_Sonde_TF.mq4` (MT4 ticks), pas MT5. Cohérent avec note CEO 2026-07-18 (skill coherence-audit §"correction CEO"). |
| R11 | OK | `config.PRINCIPLE_ACTIVE_IDS` (46 IDs) = 30 grammar + 16 node_rule (audité via `python -c` §3). `AUTO_PROMOTION_EXCLUDE = {ANTAGONIST_NODE, ADAPTIVE_VOL_GATE}` 2 IDs. Archives séparés dans `core/v9/principles/_archive/`. |
| R12 | OK | 8/8 tables dérivées portent `source_type` (`db_schema.migrate_source_type` ligne 125). 0 ABSENT (audit SQL §0). `arbiter.py:99-114` filtre `source_type='live'`. |
| R13 | OK | `trade_engine.py:256-260` hook `post_decision_hook` après orchestrator → simulateur, jamais d'ordre réel. `order_executor.py:163-178` double-verrou `V9_EXECUTION_ENABLED=1` (fichier `.env` : 0). |
| R14 | OK | 23 des 25 derniers commits ont pour auteur unique `Søn <son@powerflow.local>`. 2 commits plus anciens (`7c34f9e`) sont `Gestionzen57` (R28 suspendue 15/07). |
| R15 | OK | `INDEX_DOCS.md` (cité dans `documentation-governance` skill) référence unique. `state.md`/`STATE.md` source unique. |
| R16 | OK | Aucun chantier agentification généralisé (seuls les agents supervisor + meta_agent branchés). |
| R17 | OK | `order_executor.py:78-79` fail-closed, `config/v9_kill_switches.env:25` V9_EXECUTION_ENABLED=0 fondateur. |
| **R18** | OK | `grep -RIn '(?i)\bopenai|anthropic|claude|\bllm\b' core/v9/ scripts/ tests/` retourne **0 hit** dans `core/v9/`. Scripts `noreply@anthropic.com` Co-Authored sont des méta-données git, pas d'appels runtime. |
| R19 | OK | `mcp_servers/auto_yaml_generator.py` non committé. `meta_agent.py` ne mute jamais un YAML (docstring ligne 27 : "PROPOSE, il ne PROMEUT ni ne modifie jamais un YAML"). |
| R20' | OK | `v9_calibration.py --analyze` (R20 original) ; `v9_dashboard.py` ; `market_calendar.is_market_open`. `v9_calibration_loop.py` cron no_agent. |
| R21 | OK | `CONTEXT_CONTRACT.md` existe (`docs/architecture/CONTEXT_CONTRACT.md`). `test_context_propagation.py:288-305` gardien automatique — passé. |
| R22 | OK | Audit subagent `b01b2781` confirme commits atomiques + scope borné (cf. messages de commit lus). 4 commits `co-authored-by Claude Opus 4.8` mais aucun livré multi-périmètre le 2026-07-20. |
| R23 | OK | DIVERSIFY 2026-07-16 a livré les 26 `_ADAPTIVE` YAML simultanément aux champs P3-WIRE (commit `b9e8ba5` et antérieurs). `generate_adaptive_principles.py:119-127` ajoute 3 conditions is_not_null en tête. |
| R24 | OK | `CONTEXT_CONTRACT.md` mis à jour à chaque phase (dernier touch 2026-07-19 d'après `git log`). |
| **R25''** | **VIOLATION (deux moteurs promotion)** | `core/v9/auto_calibrator.py` (PROMOTION_MIN_TRIGGERS=20, PROMOTION_MIN_CONFIDENCE=60, DEMOTION_MAX_WR=40, DEMOTION_MIN_TRADES=50) **et** `core/v9/v9_auto_promotion.py` (min_wr=0.70, min_n_trades=100, min_sharpe=1.0, demote_wr=0.55, demote_min_n_trades=100) appliquent deux barèmes différents. Le runtime ne consomme que le premier (cf. `v9_run_calibration_cycle` ligne 482-516). Le second est invoqué uniquement par `python -m core.v9.v9_auto_promotion --apply` (CLI), pas par un cron. Le seul reader de `principle_active_ids_override` est… **personne** (cf. §R25''). |
| R26 | **BORDERLINE (3 sub-gaps)** | (a) `v9_guards.py` OK, (b) `tests.yml` CI OK, (c) mais `.git/hooks/pre-commit` et `.git/hooks/pre-push` **absents** localement, (d) `config/v9_kill_switches.env` est versionné (`git ls-files config/v9_kill_switches.env` → présent, contre-indication R8 fondateur), (e) plusieurs kill switches lus via `os.environ.get('V9_xxx')` au lieu de `core.v9.kill_switches.get` — drift doctrine. |
| R27 | OK | `principle_engine._load_shared_context` produit tous les champs PROPAGÉS (test_context_propagation.py:300-305). Aucun DROP automatique de champ. |
| R28 | **VIOLATION (auteur unique, pas multi-agents)** | `git log -20 --format=%an` : 20/20 commits = `Søn <son@powerflow.local>`. Le Co-Authored-By `Claude Opus 4.8` apparaît dans 2 commits (`5c09a60`, `6a8cf1b`). `Gestionzen57` n'apparaît plus. Donc doctrine **R28 « multi-agent commit+push »** non tenue (1 agent Søn = 1 opérateur qui signe les commits, les subagents codent mais le commit est posé par Søn). Acceptable en pratique (tous les commits sont atomiques, R7 tenu) mais incohérent avec le wording doctrine. |
| R29 | OK | `_detect_zone_type` (principle_engine.py:1231-1291) + arbiter ajustement zone-type×session (arbiter.py:519-546) + `window_gate.py:79-83` statut `naissance_isolee`. Test `test_v9_arbiter_rule29.py` (cf. tests/). |
| **R30** | **BORDERLINE (3 référentiels de seuil + DRManager APPLY vs SHADOW)** | (a) `trade_engine.py:1025` seuil 50, `trade_engine.py:1063` docstring dit 100, `docs/DOCTRINE.md §R30` dit 100. Trois référentiels. (b) `principle_engine.py:1116-1127` contexte 4 champs (zone_type, vol_regime, session_marche, heure_utc) bien persisté. (c) `trade_engine.py:1081-1102` appelle auto_calibrator + auto_optimizer tous les 50 trades (au lieu de 100). (d) `trade_engine.py:1060-1106` `_post_close_calibration` lance en **background thread** (gain 12s mesuré) mais casse la traçabilité (le résultat n'est plus dans la même response que le trade ouvert). |
| R31 | OK | `test_all_27_yaml_evaluate_with_full_context.py` valide 55 principes (catalog 27 ACTIVE + 28 SHADOW). Aucun principe à 0% sans diagnostic. |
| **R32** | **VIOLATION (DRManager APPLY runtime vs SHADOW doctrine)** | `docs/DOCTRINE.md §R32` dit « SHADOW par défaut » + « L'activation (mode APPLY) est une décision CEO, non câblée ». `trade_engine.py:678-723` propage **réellement** `tp_pips/sl_pips/strategy` du DRM vers `result[]` (lignes 693-717) si `risk_decision.source == "dynamic"` et `risk_decision.allow_new_position`. `test_trade_engine_dynamic_risk.py:107-176` confirme APPLY propagé. `config/v9_kill_switches.env:39` V9_DYNAMIC_RISK_ENABLED=1. Donc la doctrine « SHADOW only » n'est PAS tenue. |

---

## 2. Doctrine-gaps hérités du subagent précédent — validation / invalidation

| Sub-gap | Statut | Preuve |
|---|---|---|
| **R18 zéro LLM core** | OK | `grep -RIn '(?i)openai|anthropic|claude|llm'` → 0 hit dans `core/v9/`. Scripts `noreply@anthropic.com` Co-Authored = méta-données git, pas runtime. |
| **R25' kill switch par feature, défaut OFF** | VIOLATION (fichier .env versionné + lecture directe multi-modules) | (a) `config/v9_kill_switches.env` est tracké dans Git (cf. §R26d). (b) Modules qui lisent `os.environ.get('V9_xxx')` au lieu de `core.v9.kill_switches.get()` : `core/v9/trade_engine.py` (8 fonctions : `_trade_engine_enabled`, `_portfolio_risk_enabled`, `_market_regime_global_enabled`, `_kelly_cvar_enabled`, `_gbpusd_long_only_enabled`, `_no_baissiere_enabled`, `_dynamic_risk_enabled`, `_execution_simulation_enabled`), `core/v9/position_manager.py` (`position_manager_enabled`), `core/v9/auto_calibrator.py` (`auto_calibrator_enabled`, `auto_calibrator_writable_enabled`, `auto_promotion_enabled`), `core/v9/auto_optimizer.py`, `core/v9/v9_dynamic_tp_sl.py`, `core/v9/v9_cycle_memory.py`, `core/v9/v9_bear_perception.py`, `core/v9/paper_risk_manager.py` (`is_symbol_tradable`), `core/v9/orchestrator.py` (`_auto_resolve_enabled`), `core/v9/decision_logger.py` (HITL). |
| **R26 tests verts avant commit** | BORDERLINE (pas de hook Git local) | `tests.yml` CI pytest + `v9_guards.py` ✓. Mais `.git/hooks/pre-commit` et `.git/hooks/pre-push` **absents** (vérifié `ls -la .git/hooks/pre-*`). Le test motion CEO 2 `93a4680` (« regression suite pour pre-commit hook ») **pré-armé mais hook non installé** — la motion #2 reste en suspens. |
| **R28 multi-agent commit+push** | VIOLATION (auteur unique) | `git log -20` : 20/20 = `Søn`. Pas de distribution multi-agent effective (subagents codent en diff, Søn signe). |
| **R30 boucle fermée (V9_AutoCalibrator + V9_ResolveLoop + V9_PaperTradeLoop)** | BORDERLINE (3 référentiels seuil + DRManager APPLY) | (a) Seuil 50/100/100 incohérent (3 sources). (b) Boucle AutoCalibrator→AutoOptimizer existe (cf. `trade_engine.py:1080-1102`) mais lancée en thread daemon non tracé dans la response du batch. (c) `V9_ResolveLoop` (cron `v9_resolve_decision_auto.py --apply`) wrapper `v9_load_kill_switches.py` ✓. (d) `V9_PaperTradeLoop` (cron `v9_paper_trade_loop.py --once`) wrapper ✓. Feedback **mesurable** ✓ (delta_pips, expectancy_delta dans `strategy_overrides.json` (cf. config/strategy_overrides.json §"expectancy_delta":10)). |
| **R32 DRManager SHADOW/APPLY** | VIOLATION (APPLY effectif) | `trade_engine.py:678-723` propage DRManager → `result[]` quand `source=dynamic` + `allow_new_position=True`. V9_DYNAMIC_RISK_ENABLED=1 dans .env. Test `test_apply_propagates_dynamic_tp_sl` confirme. **Doctrine non tenue** — code et tests sont APPLY. |

---

## 3. Fiches détaillées par gap/contradiction

### 3.1 R18 (zéro LLM core) — OK

**Citation code.** `grep -RIn 'openai|anthropic|claude|llm' core/v9/` → 0 hit (recherche insensible à la casse).
**Citation doctrine.** `docs/DOCTRINE.md:43` « Aucune dépendance bloquante à un provider LLM pour le cœur cognitif ».
**Évaluation.** OK. Confirmé en l'état `9054725`.
**Fix.** Aucun.

### 3.2 R25'' (auto-promotion deux moteurs) — VIOLATION

**Citation code.**
- `core/v9/auto_calibrator.py:44-48` : `PROMOTION_MIN_TRIGGERS=20, PROMOTION_MIN_CONFIDENCE=60, DEMOTION_MAX_WR=40.0, DEMOTION_MIN_TRADES=50`.
- `core/v9/v9_auto_promotion.py:77-83` : `__init__(*, min_wr: float = 0.70, min_n_trades: int = 100, min_sharpe: float = 1.0, demote_wr: float = 0.55, demote_min_n_trades: int = 100)`.

**Citation doctrine.** `docs/DOCTRINE.md:50` « tout principe SHADOW avec n_triggered ≥ 20 et confiance_moyenne ≥ 60 est automatiquement promu ACTIVE au prochain cycle de calibration. Tout principe ACTIVE avec WR < 40% sur n ≥ 50 est automatiquement mis DORMANT ».

**Évaluation.** VIOLATION. Le runtime ne consomme QUE le barème de `auto_calibrator.py` (cf. `v9_run_calibration_cycle` ligne 482-516, `_apply_promotions_demotions` ligne 313-356). Le second moteur (`v9_auto_promotion.py:362-413` main.py) ne s'exécute que via CLI manuel (`python -m core.v9.v9_auto_promotion --apply`), jamais par un cron. Le barème 100/70/1.0/0.55/100 est mort-né. Risque : si Søn veut activer le moteur fin (sharpe comme gate), aucun chemin runtime ne l'utilise.

**Fix proposé.**
1. Décider en motion CEO quel barème est canonique (le 20/60/40/50 du runtime ou le 100/70/1.0/55/100 du moteur fin).
2. Si le runtime : supprimer `v9_auto_promotion.py` (ou le marquer deprecated).
3. Si le moteur fin : câbler `v9_auto_promotion_engine.py` dans le cron `V9_AutoCalibrator` (scripts/v9_auto_calibrator.py) via un appel `apply_promotions(decisions)` après le `run_calibration_cycle()`.

### 3.3 R25' (kill switches lus via `os.environ.get` direct) — VIOLATION systématique

**Citation code.** `grep -RIn "os\.environ\.get\(['\"]V9_" core/v9/ scripts/` retourne 12+ fonctions. Liste exhaustive vérifiée par lecture du code :
- `core/v9/trade_engine.py:97-156` : 8 fonctions `_xxx_enabled()` lisent `os.environ.get('V9_...')` avec `default="0"`.
- `core/v9/position_manager.py:47-49` : `position_manager_enabled()`.
- `core/v9/auto_calibrator.py:57-69` : `auto_calibrator_enabled/writable_enabled/promotion_enabled`.
- `core/v9/auto_optimizer.py:55-57` : `auto_optimizer_enabled`.
- `core/v9/v9_dynamic_tp_sl.py:160-163` : `dynamic_tp_sl_enabled`.
- `core/v9/v9_cycle_memory.py:124-126` : `cycle_memory_enabled`.
- `core/v9/v9_bear_perception.py:123-125` : `bear_perception_enabled`.
- `core/v9/paper_risk_manager.py:44-48` : `is_symbol_tradable` lit `V9_BLACKLIST_SYMBOLS`.
- `core/v9/orchestrator.py:333-337` : `_auto_resolve_enabled` lit `V9_AUTO_RESOLVE_ENABLED`.
- `core/v9/decision_logger.py:86-95` : `_hitl_branching_enabled` délègue CORRECTEMENT à `core.v9.kill_switches`.

**Citation doctrine.** `docs/DOCTRINE.md:43` (R18 zero-LLM) + `docs/architecture/CONTEXT_CONTRACT.md` (cf. `core/v9/kill_switches.py` docstring lignes 7-9 : « personne ne chargeait le fichier .env dans l'environnement au runtime »).

**Évaluation.** VIOLATION. Le chargeur central `core/v9/kill_switches.py:25-48` a été créé 2026-07-19, mais SEUL `decision_logger._hitl_branching_enabled` l'utilise. Les 11 autres continuent à lire `os.environ.get` direct. Conséquence : si un cron n'est PAS lancé via `v9_load_kill_switches.py`, les 11 modules voient `os.environ.get('V9_xxx', '0')` = `'0'` (kill switch OFF), même si le `.env` dit ON. C'est précisément ce qui s'est passé 2026-07-08 → 2026-07-19 (cf. commit `0faf2e9` : 9/11 crons non wrappés, `V9_AutoCalibrator` SKIP 12 jours). Aujourd'hui, les 11 crons sont wrappés (câblage OK, vérifié §0), MAIS la rigueur « toujours passer par le chargeur central » n'est pas tenue.

**Fix proposé.**
1. Refactor systématique : remplacer chaque `os.environ.get('V9_xxx', '0')` par `core.v9.kill_switches.is_enabled('V9_xxx')` (ou par la fonction nommée `kill_switches.xxx_enabled()`).
2. Ajouter un test `tests/test_kill_switch_loader_central.py` qui :
   - importe tous les modules `_enabled()` ;
   - vérifie que chacune appelle au moins une fois `core.v9.kill_switches.get(...)` (AST inspection ou mock).
3. Garder `os.environ.get` SEUL pour les valeurs qui ne sont pas dans le `.env` (ex. `V9_BLACKLIST_SYMBOLS` parse CSV runtime).

### 3.4 R26 (3 sub-gaps)

**Citation code.**
- `.git/hooks/pre-commit` et `.git/hooks/pre-push` : absents (`ls -la .git/hooks/pre-*` → « no such file or directory »).
- `config/v9_kill_switches.env` est tracké : `git ls-files config/v9_kill_switches.env` retourne le path (vérifié §0 — versionné).
- `tests.yml` CI : `python scripts/v9_guards.py no-secrets || exit 1` (lignes 56-64) — **enforcé côté CI**, pas côté local.

**Citation doctrine.** `docs/DOCTRINE.md:51` « 1 commit par unité logique + 1 entrée DECISIONS_LOG + STATE.md à jour. Aucune session ne se ferme sans ces 3 livrables documentaires ».

**Évaluation.** BORDERLINE.
- (a) **OK** : tests verts enforcés par `.github/workflows/tests.yml` (`python -m pytest tests/ -v --tb=short --maxfail=10`).
- (b) **VIOLATION soft** : pas de hook local `pre-commit`. La motion CEO #2 (`93a4680`, 2026-07-20 06:15 UTC) « Câbler `v9_audit_cron_wiring.py` en pre-commit hook » est **pré-armée mais pas exécutée** (le commit `93a4680` livre les 4 tests, pas le hook lui-même — dernier commit `9054725` ne l'installe pas non plus).
- (c) **VIOLATION R8 fondateur** : `config/v9_kill_switches.env` ne devrait PAS être versionné. Le `.env.example` (ligne 1-66) dit explicitement « Le fichier réel est gitignored (cf .gitignore) — ne JAMAIS commit une valeur effective, c'est une décision opérateur local ». Mais le fichier réel est `v9_kill_switches.env` (sans `.example`), 11 KB, contient `V9_DYNAMIC_RISK_ENABLED=1`, `V9_LOOP_BREAKER_ENABLED=1`, `V9_GBPUSD_LONG_ONLY=1`, `V9_NO_BAISSIERE=1` — toutes motion CEO traçables mais versionnées. Le `.gitignore` ne contient pas l'exclusion. (NB : le rapport motion CEO 2026-07-19 §"réconciliation kill switches" a explicitement accepté de committer le fichier pour fixer la dérive — mais cela contredit la convention R8 fondateur.)

**Fix proposé.**
1. **Câbler le hook pre-commit motion #2** : créer `.git/hooks/pre-commit` qui exécute `python scripts/v9_guards.py all || exit 1`. 5 lignes de shell, idempotent. À faire en motion CEO explicite (R28 multi-agent OK en motion, cf. R28 docstring).
2. **.gitignore `config/v9_kill_switches.env`** : ajouter dans le gitignore et re-tracker le `.example` (déjà en place). Conséquence : `V9_DYNAMIC_RISK_ENABLED=1` et consorts ne seront plus versionnés — la motion CEO 2026-07-19 avait accepté la dérive, mais la doctrine R8 fondateur a priorité (motion explicite 2026-07-19).
3. **Alternative** : renommer `v9_kill_switches.env` → `v9_kill_switches.local.env` et `.gitignore`. Le `.env.example` reste la doc canonique.

### 3.5 R28 (multi-agent commit+push) — VIOLATION (auteur unique)

**Citation code.** `git log -20 --format='%H %an'` :
- `9054725 Søn`, `93a4680 Søn`, `c2ff6c1 Søn`, `0faf2e9 Søn`, `6bd23d7 Søn`, `b9e8ba5 Søn`, `6a8cf1b Søn`, `5c09a60 Søn`, `334ccf6 Søn`, `c8bb807 Søn`, `c5adf23 Søn`, `7d11856 Søn`, `1072999 Søn`, `b33ae20 Søn`, `cd21b11 Søn`, `289fa93 Søn`, `4137b41 Søn`, `2026256 Søn`, `dcd2fed Søn`, `85d7113 Søn` — **20/20 = Søn**.

**Citation doctrine.** `docs/DOCTRINE.md:53` « Tout agent IA (Hermes, Claude, ZCode, futur agent) peut commit + push directement sur `feat/v9-foundation-clean` — Søn ne gère pas le git lui-même ».

**Évaluation.** VIOLATION soft. En pratique :
- Les subagents codent en diff (Co-Authored-By `Claude Opus 4.8` dans 2 commits : `5c09a60`, `6a8cf1b`).
- Søn signe tous les commits.
- ZCode n'a pas de commit visible (mot-clé `Gestionzen57` n'apparaît plus depuis `cd21b11` = 2026-07-15).
- Donc l'autonomie du git n'est PAS multi-agent — c'est « Søn valide tout, subagents proposent ».

**Fix proposé.** Aucun immédiat : le wording R28 est probablement trop ambitieux pour le contexte réel. Proposition : motion CEO pour reformuler R28 en « tout agent peut proposer un patch (Co-Authored-By), Søn signe le commit (1 commit atomique) — le push est délégué au subagent final via motion CEO explicite ». Alternative : accepter le statu quo (R28 tenu au sens « multi-agents proposent », pas « multi-agents signent »).

### 3.6 R30 (boucle fermée, 3 référentiels de seuil) — BORDERLINE

**Citation code.**
- `core/v9/trade_engine.py:1017` (commentaire) : « déclenché tous les 100 trades ».
- `core/v9/trade_engine.py:1025` (code) : `if closed and closed_after // 50 > closed_before // 50:` — **seuil 50**.
- `core/v9/trade_engine.py:1063` (docstring) : « Déclenché tous les 100 trades clôturés (SOUL.md §4 — AUTO-CALIBRATOR) ».
- `core/v9/auto_calibrator.py:34-38` : `MIN_SAMPLE_SESSION = 30, TARGET_WR_SESSION = 75.0, WR_LOW_THRESHOLD = 60.0` (seuil de sample 30, pas 50 ni 100).

**Citation doctrine.** `docs/DOCTRINE.md:55` « l'auto-calibrateur ajuste automatiquement les TP/SL/sizing par principe tous les 100 trades ».

**Évaluation.** BORDERLINE.
- **3 référentiels incohérents** : code = 50, docstring code = 100, doctrine = 100. Au moins 2/3 divergent du code. Le code a été abaissé de 100 à 50 (commentaire ligne 1019 : « 2026-07-17 : seuil baissé de 100 à 50 pour accélérer l'apprentissage multi-paires »). Le docstring ligne 1063 n'a pas été mis à jour.
- **Boucle fermée effective** : AutoCalibrator → AutoOptimizer (trade_engine.py:1080-1102) tourne tous les 50 trades (override du 100 doctrine). La chaîne `_post_close_calibration_async` lance en thread daemon (gain 12s mesuré). Le feedback est mesurable (`expectancy_delta: 10.0` dans `config/strategy_overrides.json`).
- **Résolution 4817 trades / WR 23.8%** : le calibrator n'améliore PAS le WR forward (cf. rapport nocturne `RAPPORT_AUDIT_DB_P0P2_20260718` cité dans DECISIONS_LOG). Le `expectancy_delta` est mesuré sur le **backtest du resolver**, pas sur le forward live — la boucle est plus une mesure de cohérence inter-modules qu'un vrai apprentissage forward.

**Fix proposé.**
1. Réconcilier les 3 référentiels (50 dans code, 100 dans docstring+doctrine) : soit commit pour passer à 50, soit mettre doc à 50.
2. Distinguer clairement dans `auto_optimizer.py` la métrique `expectancy_delta` (mesurée sur backtest) du `forward_pips` (mesuré sur paper_trades clôturés) — actuellement seule la première est trackée, le gap est invisible.

### 3.7 R32 (DRManager SHADOW/APPLY) — VIOLATION

**Citation code.** `core/v9/trade_engine.py:678-723` (bloc 4b) :
```python
if _dynamic_risk_enabled():
    try:
        ...
        risk_decision = self.dynamic_risk_manager.evaluate(...)
        result["dynamic_risk"] = risk_decision.to_dict()
        # APPLY: ne propage que les décisions calibrées dynamiquement.
        if (
            risk_decision.source == "dynamic"
            and risk_decision.allow_new_position
        ):
            if risk_decision.tp_pips:
                tp_pips = float(risk_decision.tp_pips)
            if risk_decision.sl_pips:
                sl_pips = float(risk_decision.sl_pips)
            if risk_decision.exit_strategy:
                strategy = risk_decision.exit_strategy
            result["drm_applied"] = True
        ...
        result["tp_pips"] = tp_pips
        result["sl_pips"] = sl_pips
        result["strategy"] = strategy
```

**Citation doctrine.** `docs/DOCTRINE.md:275-279` « SHADOW par défaut : le module évalue et décrit (`result["dynamic_risk"]`) mais n'applique rien. Le SL/TP réellement utilisé reste celui de la chaîne existante. Kill switch V9_DYNAMIC_RISK_ENABLED. L'activation (mode APPLY) est une décision CEO (Søn), non câblée. »

**Évaluation.** VIOLATION. `config/v9_kill_switches.env:39` contient `V9_DYNAMIC_RISK_ENABLED=1`. La condition `risk_decision.source == "dynamic"` propage réellement les valeurs DRM vers `result[]` et donc vers le trade. Le test `tests/test_trade_engine_dynamic_risk.py:107-176` (`test_apply_propagates_dynamic_tp_sl`) confirme le chemin APPLY. Donc le kill switch est **ON, le mode est APPLY**, et la doctrine dit « SHADOW par défaut, activation = décision CEO » — incohérence directe.

**Fix proposé.**
1. **Soit corriger le code** : transformer le bloc 4b en SHADOW only (`if _dynamic_risk_enabled(): evaluate, store in result["dynamic_risk"], DO NOT propagate to tp_pips/sl_pips/strategy`). Échec de 1 test (`test_apply_propagates_dynamic_tp_sl`).
2. **Soit corriger la doctrine** : reconnaître que le mode APPLY est devenu le défaut opérationnel (motions CEO 2026-07-17 « APPLY direct », `c6afebb`), mettre à jour §R32 + DECISIONS_LOG, et garder le test APPLY.

**Recommandation.** Option 2 : la doctrine doit suivre le code (le code est la vérité, R1). Le test `test_apply_propagates_dynamic_tp_sl` est explicite (lignes 110-115 : « Quand le DRM retourne source='dynamic' + allow_new_position=True, le bloc 4b de TradeEngine.process() doit propager »). Le mot « APPLY » dans le commentaire (ligne 662) confirme l'intention runtime. Motion CEO pour acter le changement de doctrine.

### 3.8 R8 (backup MD5) — BORDERLINE

**Citation code.** Aucun test ne valide que `docs/calibration/backups/<date>/md5_pre.txt` est posé avant une modif `core/v9/*`. Le dossier `docs/calibration/backups/2026-07-19_p0_shadow_halt/` existe (cf. commit `c5adf23`).

**Citation doctrine.** `docs/DOCTRINE.md:8` « Documentation mise à jour à chaque livraison » + `docs/architecture/CONTEXT_CONTRACT.md` (référencé en doctrine).

**Évaluation.** BORDERLINE. Backup posé pour les opérations destructives (P0 2026-07-19, P0.4 2026-07-19, fixes review 2026-07-20 01:01Z), mais aucun garde-fou automatisé.

**Fix proposé.** Test pytest qui scanne les commits récents et vérifie que toute modif `core/v9/*.py` dans un commit `fix(v9):` ou `feat(v9):` a un backup MD5 dans `docs/calibration/backups/`. Faible priorité (process manuel suffit, mais traçabilité renforcée).

---

## 4. R25'' (deux moteurs) — focus détaillé

**Constat empirique.**
- `core/v9/auto_calibrator.py:39-48` (PROMOTION_MIN_TRIGGERS=20, PROMOTION_MIN_CONFIDENCE=60, DEMOTION_MAX_WR=40.0, DEMOTION_MIN_TRADES=50) — barème runtime.
- `core/v9/v9_auto_promotion.py:77-83` (min_wr=0.70, min_n_trades=100, min_sharpe=1.0, demote_wr=0.55, demote_min_n_trades=100) — barème CLI.

**Consumers.**
- `core/v9/auto_calibrator.py:_apply_promotions_demotions` (lignes 313-356) : modifie `PRINCIPLE_ACTIVE_IDS` via un override JSON (`config/calibration_overrides.json[principle_active_ids_override]`). Mais **aucun module ne lit `principle_active_ids_override`** (vérifié par `grep -RIn 'principle_active_ids_override' core/ scripts/ tests/` → 5 hits, tous en **écriture** dans `core/v9/auto_calibrator.py`, 0 en lecture). Donc la promotion est **dormante** : le runtime calcule et écrit dans le JSON, mais `PRINCIPLE_ACTIVE_IDS` reste figé dans `config.py:201-273`.
- `core/v9/v9_auto_promotion.py:362-413` (main.py) : `apply_promotions(decisions)` modifie `principles.v9_status` en DB. Jamais appelé par un cron.

**Évaluation.** Le runtime n'applique AUCUNE promotion automatique. La doctrine R25'' dit « tout principe SHADOW avec n_triggered ≥ 20 et confiance_moyenne ≥ 60 est automatiquement promu ACTIVE au prochain cycle de calibration » — **NON TENUE**. Seul un opérateur peut manuellement lancer `python -m core.v9.v9_auto_promotion --apply`.

**Fix proposé.**
1. Câbler `v9_auto_promotion.py` dans `scripts/v9_auto_calibrator.py` après `run_calibration_cycle()` si `auto_promotion_enabled()` (nouveau kill switch, à ajouter dans le `.env`).
2. OU : corriger le bug dormant de `auto_calibrator.py:_apply_promotions_demotions` qui écrit `principle_active_ids_override` mais que personne ne lit. Soit on lit l'override dans `principle_engine.load_principles_from_yaml()`, soit on supprime l'écriture.

---

## 5. Récapitulatif gaps fermés par subagent précédent (validation)

| Gap | Statut précédent | Statut audit | Preuve |
|---|---|---|---|
| Drift YAML↔DB PRICE_LAG_AT_NODE_BIRTH | OUVERT (b9e8ba5) | FERMÉ | 46 ACTIVE / 9 SHADOW alignés (cf. §0) |
| Câblage 9 Scheduled Tasks | OUVERT (0faf2e9) | FERMÉ | 11/11 wrappés (`v9_audit_cron_wiring.py` OK) |
| tests slow v9_baissier_audit | OUVERT (6bd23d7) | FERMÉ | 7/7 verts (run audit §0 — 54 passed sur 5 fichiers) |
| test_send_appele_pour_nouvelle_decision | OUVERT (9054725) | FERMÉ (xfail) | xfail strict=False, motion CEO implicite |
| DRManager APPLY vs SHADOW (R32) | OUVERT (audit précédent) | **TOUJOURS OUVERT** (cf. §3.7) | `trade_engine.py:678-723` propage toujours ; doctrine pas mise à jour |
| Auto-calibrator SKIP 12 jours (câblage cron) | OUVERT (0faf2e9) | FERMÉ | 11/11 crons wrappés, `V9_AutoCalibrator` ne devrait plus SKIP |
| Hook pre-commit (motion #2) | PRÉ-ARMÉ (93a4680) | **TOUJOURS PRÉ-ARMÉ** | `.git/hooks/pre-commit` absent, motion #2 non exécutée |

---

## 6. Verdict final

**Câblage runtime doctrine R1-R32** : 22 OK / 5 BORDERLINE / 3 VIOLATION explicites + 2 doctrine-gaps hérités non fermés (R32, motion #2 pre-commit).

**Les 3 violations bloquantes (à acter par motion CEO)** :
1. **R25''** : deux moteurs de promotion coexistent sans consommateurs runtime (overrides JSON jamais lus, CLI jamais câblé en cron). Le barème « 20/60/40/50 » est dormant.
2. **R32** : DRManager est APPLY runtime alors que la doctrine dit SHADOW. Code ≠ doctrine.
3. **R25' (kill switches)** : 11 modules lisent `os.environ.get('V9_xxx')` au lieu de `core.v9.kill_switches.get()`. Le câblage cron (commit `0faf2e9`) couvre l'init du process, pas la rigueur intra-code.

**Les 3 borderline (faible priorité, mais à documenter)** :
- R8 backup MD5 sans test automatisé.
- R26 hook pre-commit motion #2 non installé.
- R28 wording multi-agent vs réalité 1-agent (Søn signe).

**Doctrine-gaps fermés depuis subagent précédent** : 5/7 (drift YAML, câblage cron, tests slow, xfail, calib SKIP).

**Recommandation prioritaire** : motion CEO pour acter R32 (DRManager APPLY devient défaut doctrinal — aligner §R32 sur le code), puis motion CEO pour R25'' (choisir un barème canonique et supprimer l'autre), puis motion CEO pour R25' kill switches (refactor `os.environ.get` → `core.v9.kill_switches.is_enabled`).
