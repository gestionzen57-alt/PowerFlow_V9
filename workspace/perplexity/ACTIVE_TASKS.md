# ACTIVE_TASKS — Workspace Perplexity

Synthèse opérationnelle des tâches. La source de vérité détaillée reste
`docs/STATE.md` (dernière mise à jour **2026-07-13 — série Autopilot CEO P1+P6 + Brief O4 résolu**).
Ce fichier ne fait qu'organiser la même information par statut d'exécution
pour une reprise rapide. **Resync 2026-07-13** (série Autopilot livrée + O4
résolu — P1 sert désormais asie/london/overlap, NY/after blacklistés).

## Terminé — série Autopilot CEO 2026-07-13 (« go fait tout, tu orchestres »)

Mandat CEO reçu ~00:30 UTC sur 6 actions prioritaires identifiées lors du diagnostic
stratégique quant senior. État final sur `feat/v9-foundation-clean` :
**1114 verts + 2 skipped + 0 fail** (résolution de la dernière régression).

- **P6** ✅ — `core/v9/vol_regime.py` (module pur 197 LOC) — ATR-30 → LOW/NORMAL/HIGH/EXTREME,
  calibration empirique 9970 fenêtres M15 GBPUSD (P25=2.13, P50=3.20, P75=5.50, P95=11.34 pips),
  intégration `principle_engine._load_shared_context()` sous 3 clés `vol_regime` /
  `vol_atr_pips` / `vol_regime_level`. Commit `9592ce3`. 30 tests verts.
- **P1** ✅ — 3 colonnes `signals.(exit_strategy_recommended, tp_pips_recommended,
  sl_pips_recommended)` peuplées par `session_marche` via DYNAMIC_PROFILES. Migration
  rétrocompatible `_ensure_column`. Commit `331382f`. 7 tests verts.
- **Fix HITL** ✅ — `tests/test_decision_logger_hitl_branching.py` adapté au seuil CEO
  2026-07-13 `HITL_CONF_HIGH=80` (1 test obsolète `test_conf_above_65_*` remplacé par 2
  tests cohérents : `test_conf_above_80_high_silent_no_notification` +
  `test_conf_at_80_still_in_informative_band`). Commit `ade60e1`.
- **Brief O4** ✅ — politique conservatrice Søn tranchée 13/07 ~01:50 UTC : New York et
  After blacklistées (exclusion structurelle). Commit `bd1ca6f`. `core/v9/exit_simulator.py`
  expose `DYNAMIC_BLACKLIST_SESSIONS = frozenset({"new_york","after"})` +
  `is_session_tradable(session)`. `signal_generator._recommend_dynamic_*` retourne
  `strategy=None` pour ces sessions, `decision_logger._determine_action` defense-in-depth
  sélectif (force `aucune_action` si exit_strategy_recommended=None ET direction directionnelle).
  **P1 sert désormais asie/london/overlap uniquement** (sessions tradables). 18 tests verts.
- **Docs** ✅ — `logs/autopilot_status.md` créé (Telegram runtime cassé → status local
  conformément R6). `docs/STATE.md` mis à jour (nouvelle section série Autopilot).
  Commit `6cf75d4` (status doc seul) + commits consolidation `9aa7d08`/`0b29280`/
  `96232dd`/`ee084f1`/`3b9f7fe`/`b48732c`/`87aca1e` + Brief O4 DECISIONS_LOG `fc92ac1`.

**Limites assumées** (rappel doctrinal) :
- Telegram status runtime cassé (placeholder sanitisé, vrai token ailleurs) — status
  déposé dans `logs/autopilot_status.md`, conformément R6 (pas de simulation de succès).
- Activation P1 effective **sur asie/london/overlap** depuis O4 (commit `bd1ca6f`).
  Les résolveurs WIN/LOSS ne lisent pas encore `signals.exit_strategy_recommended` —
  chantier séparé post-décision O4 (maintenant résolue).

## Terminé — 2026-07-14 (ORDER-BRIDGE + P2 Shadow mode, feu vert Søn sans blocage)

- **ORDER-BRIDGE** ✅ — commit `3e01eca`. `core/v9/order_queue_watcher.py`
  + CLI `scripts/v9_order_queue_watcher.py`. 12 tests verts.
- **P2 Shadow mode** ✅ — commit `0c0c334`. `core/v9/shadow_evaluator.py` +
  hook `orchestrator.run_chain()` (gated `V9_SHADOW_MODE_ENABLED` OFF) +
  `scripts/v9_shadow_divergence_report.py`. 24 tests verts. 3 pièges de
  corruption identifiés/neutralisés en cours d'implémentation — détail
  DECISIONS_LOG §2026-07-14.
- **Docs** ✅ — commit `66ad179`. `docs/STATE.md` + DECISIONS_LOG +
  `ROADMAP_CLAUDE_CODE.md` (table AUTORISÉS entièrement clôturée, nouvelle
  section "Chantiers PROPOSÉS").
- **Tests finaux** : 1249 → **1285 verts + 2 skipped + 0 fail**.
- **Push** : effectué sur confirmation explicite Søn (commit `66ad179`).

## En cours — anciennement "suite Autopilot" (P3/P4/P5/P2 tous livrés — table conservée pour historique)

| # | Chantier | Effort | Priorité | Notes |
|---|----------|--------|----------|-------|
| ~~**P3**~~ | ~~Adaptive Thresholds~~ | — | — | Module+wire-up faits (`5abfa2b`, `1babf14`). Reste : P3-CONSUME (voir ROADMAP_CLAUDE_CODE.md §Proposés). |
| ~~**P4**~~ | ~~Event Calendar dynamique~~ | — | — | Fait, commit `05f8232`. |
| ~~**P5**~~ | ~~Long-term memory~~ | — | — | Fait, commit `c84aba4`. |
| ~~**P2**~~ | ~~Shadow mode parallèle~~ | — | — | Fait, commit `0c0c334` (2026-07-14). |

## Prochains candidats (aucun autorisé — voir `ROADMAP_CLAUDE_CODE.md` §Chantiers PROPOSÉS)

- **P3-CONSUME** (HAUTE, 6-10h) — consommer réellement `adaptive_*_threshold`
  dans `evaluate_condition`/YAML (aujourd'hui purement descriptif).
- **SHADOW-EXPAND** (MOY, 2-4h) — étendre `SHADOW_ENV_OVERRIDES` à
  trader_mini_weigher / auto_calibrator.
- **P1-RESOLVE** (MOY, ~4h) — patch `v9_resolve_decision_auto.py` pour lire
  `signals.exit_strategy_recommended`. Décision Søn requise avant ouverture.
- **TELEGRAM-RUNTIME** (opérationnel, pas code) — vrai token Telegram,
  bloque `v9_shadow_divergence_report.py --send` en pratique.

## Clôturé — série de briefs O1-O5 (2026-07-12)

Tous livrés. Catalogue final : 25 ACTIVE + 1 SHADOW. Résolveur live : DYNAMIC (Brief O1).
Dataset V9-trader-mini exporté (Brief O5).

## Clôturé — série Q1→Q5 « saut quantique » (2026-07-13, session Claude Code parallèle)

Mandat confirmé en session (distinct du document `FABLE_QUANTUM_LEAP_PROMPT.md`) — voir
`workspace/perplexity/memory/DECISIONS_LOG.md` §"2026-07-12 — Série Q1→Q5". Tous les briefs
autorisés livrés : Q1 (trader-mini, gated OFF), Q2 (auto-calibrateur, gated OFF), Q3
(dashboard HITL), Q4 (multi-paires), Q5 volet VPS (exécution réelle exclue). **1191 verts +
2 skipped**, 15 fails pré-existants `test_telegram_notifier.py` inchangés (chantier TG-FIX
réservé). `core/v9/order_executor.py` **jamais écrit** — reste gelé, confirmation explicite
distincte requise. Checkpoint : `docs/checkpoints/CHECKPOINT_20260713_QUANTUM_LEAP.md`.

## Prochaines actions
1. **Push** — effectué par la session Claude Code sur instruction explicite et directe de
   l'utilisateur 2026-07-13 (dérogation ponctuelle à R28, Hermes étant inactif au moment du
   push ; voir DECISIONS_LOG pour la trace). Couvre les commits Autopilot P1+P6+Fix HITL+O4
   ET la série Q1→Q5.
2. **Lancer P3** (Adaptive Thresholds) en prochaine session — chantier le plus
   impactant (seuils `f(vol_regime, news_proximity)` → probant à runs successifs).
3. **Fixer les 15 fails pré-existants** de `tests/test_telegram_notifier.py`
   (refactoring Telegram post-bug 2026-07-11, indépendant Autopilot série).
4. **Activer P1 effective** (post-O4 résolu) — patch `v9_resolve_decision_auto.py`
   pour lire `signals.exit_strategy_recommended` (chantier ~4h, distinct).
5. **Post-open Asian session lundi 22h UTC** (= 23h Paris heure d'été) — vérifier
   que le pipeline live capte les nouveaux snapshots et que les nouveaux
   filtres O4 rejettent NY/after.
4. **Découverte notée, non ouverte (R22)** — `paper_trades.pips_simulated`
   n'est pas resynchronisé avec les nouveaux labels DYNAMIC (dernier sync sur
   les 1105 décisions du 2026-07-11 uniquement).

## Gelé (ne pas démarrer)
- **Phase 10** (fédération d'agents) — inchangé, aucune date planifiée.
- **Phase 12 — exécution d'ordres réelle** (`core/v9/order_executor.py`) — **toujours gelée**
  (`AGENT.md` §Périmètre GELÉ, « interdit fondateur » `docs/ROADMAP.md`). Le déploiement VPS
  (Q5 volet 1, crons/heartbeat) N'est PAS concerné par ce gel et peut avancer. Seule l'écriture
  du module de placement d'ordres réel est bloquée, en attente d'une confirmation explicite et
  distincte de l'utilisateur (pas couverte par le mandat Q1→Q5 du 2026-07-12).
- **Skills/agents auto-générés** — inchangé.
- ~~**Entraînement V9-trader-mini** (Brief O5)~~ → **dégelé 2026-07-12** (Brief Q1, voir
  §En cours), sous condition étape 0 (investigation rupture val) + gate accuracy<60%.

## Terminé récemment

### 2026-07-11/12 — Phase 13.2 → 13.3, série de briefs O1-O5
- ✅ **Ménage Phase 13 CEO** (2026-07-11) — 71 paper trades clôturés, 102
  décisions résiduelles résolues, 0 décision non résolue (9516/9516, 100%).
- ✅ **Phase 13.2** (2026-07-11) — ExitSimulator/PaperRiskManager/
  PyramidingEngine/PrincipleScorer livrés, analyse 16 stratégies de sortie,
  stratégie DYNAMIC implémentée.
- ✅ **Briefs O1→O5** (2026-07-12) — cf. §En cours ci-dessus pour le détail.
  Référence complète : `workspace/perplexity/memory/DECISIONS_LOG.md`
  §2026-07-12 (6 entrées datées, une par brief).

### Phase 13 CEO + H24 autopilot (2026-07-10)
- **CONFIANCE_MIN 80 → 70** (core/v9/risk_manager.py) — biais inverse RiskManager prouvé.
- **Arbiter zone_type=neutre recalibré** (-7 asie/london, -6 after/ny).
- **YAML SIGNAL_OPEN SHADOW** créé (1ère proposition meta-agent validée).
- **Catalogue 25 ACTIVE + 1 SHADOW = 26 YAMLs**.
- **930 tests verts, 0 régression** (+52 depuis 878).
- **Bus apprentissage réveillé** : 224 events émis sur 24h, 5 propositions meta-agent.
- **5 skills V9 livrées** : phase13-recalibration, meta-agent, paper-trade-offline, replay-param, mcp-architecture.
- **Architecture MCP recommandée** (5 serveurs ciblés anti-V8 monolithique, chantier Phase 11 gelé).

### Antérieur (juillet 2026)
- ✅ **Sprint Søn Mode A livré** (2026-07-07 21h → 22h30) — 6 commits sprint,
  Mode A agentification bornée + télémétrie + VPS-ready + audit V8/V9 + Règle 30.
  Tests 637 → 663 verts. 0 régression.
- ✅ **Règle 30 ajoutée** (2026-07-07 22h) — apprentissage conditionnel WIN/LOSS
  avec seuils progressifs 5/20/50/200 (repères, règle 25 respectée).
- ✅ **Règle 29 LIVRÉE** (2026-07-07 17h45 → 20h55) — 14 commits, doctrine §3.1+§3bis+§6+§8
  import V8 → V9, zone_type persistence, naissance_isolee window, HITL renforcé,
  arbiter pondération zone-type×session, tests dédiés (32+ verts).
  Ref. : `docs/checkpoints/CHECKPOINT_20260707_RULE29.md`.
- ✅ **Dette 10/10 résolue** (2026-07-07) — F-10 à F-19 (CHANGELOG, LICENSE, CI, etc.).
- ✅ **Phase 9.9 CONSOLIDATION-COMPLETE** (2026-07-07) — 14 sous-chantiers C-1→F-9.
- ✅ **Phase 9.7 + 9.8 livrées** (2026-07-07) — paper-trade simulator + heartbeat VPS-READY.
- ✅ **Phase 9 livrée** (2026-07-05) — chaîne cognitive 9 couches complète, 214 tests.
- ✅ **Phase 9.5** (2026-07-05) — outillage ops + mini-checkpoints + runbook, 40 tests.
- ✅ **2026-07-06** — ZoneDetector + Grammaire (9/9 node_rule ACTIVE), 283 tests.
- ✅ **2026-07-06** — Stabilisation live Phase 9 confirmée (flux EA MT4).
- ✅ **2026-07-06** — Session 4 YAML news-aware (4 principes enrichis, commit `a87d88f`).
- ✅ **2026-07-06** — Inventaire migration V8→V9 (audit MIGRATION_POLICY_V9.md).
- ✅ **2026-07-06** — Nettoyage 7 docs stales (alignement zone_diagnostics).
- ✅ **2026-07-07** — COALITION_THRESHOLD 5.0 → 5.38 (London open, commit `fb5383a`).
- ✅ **2026-07-07** — Telegram Notifier GBPUSD live (scripts/v9_telegram_notifier.py).
- ✅ **2026-07-07** — Fix signal_generator currency gap (commit `8697d84`).

## Recommandation pour chantier futur distinct (non démarré)
- **Refactor arbiter.py** : accepter conn optionnelle en paramètre (permet
  tests in-memory propres). Non résolu par le Brief O2 (2026-07-12) — la
  pondération PrincipleScorer a été ajoutée sans changer cette API.
- ~~Décision DST-aware `market_calendar.py`~~ → **RÉSOLU** (commit `e42d81b`,
  2026-07-07, `America/New_York` + `zoneinfo`). Ouverture dimanche = 23h
  Paris = **21h UTC en heure d'été** (22h UTC en heure d'hiver) — vérifié
  cohérent dans le Brief O1 (fenêtre d'exécution 2026-07-12).
