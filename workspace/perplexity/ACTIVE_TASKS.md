# ACTIVE_TASKS — Workspace Perplexity

Synthèse opérationnelle des tâches. La source de vérité détaillée reste
`docs/STATE.md` (dernière mise à jour **2026-07-12 — série de briefs O1→O5**).
Ce fichier ne fait qu'organiser la même information par statut d'exécution
pour une reprise rapide. **Resync 2026-07-12 (Brief R)** — la section "Phase 13
CEO + H24 autopilot" et les prochaines actions ci-dessous datent du 2026-07-10
et référençaient un état largement dépassé (930 tests, WIN/LOSS non résolues,
premier paper trade attendu en août) ; remplacées par l'état réel post-O1→O5.

## En cours — série de briefs Q1→Q5 « saut quantique » (2026-07-12, post O1→O5+R)

Mandat reçu en session (autopilot encadré) — voir `workspace/perplexity/memory/DECISIONS_LOG.md`
§"2026-07-12 — Série Q1→Q5" pour le détail exact du périmètre confirmé et de ce qui en est
explicitement exclu (exécution d'ordres réelle, gelée par `AGENT.md`, confirmation distincte requise).

- **Q1** 🔄 — V9-trader-mini : investigation rupture val → baseline tabulaire → intégration
  gated (`V9_TRADER_MINI_ENABLED=0`).
- **Q2** ⏳ — Auto-calibrateur (`core/v9/auto_calibrator.py`), propose-only, `V9_AUTO_CALIBRATOR_ENABLED=0`.
- **Q3** ⏳ — Dashboard web HITL (lecture seule + table `hitl_reviews` dédiée).
- **Q4** ⏳ — Multi-paires EURUSD/USDJPY/GBPJPY (audit d'impact d'abord, non-régression GBPUSD).
- **Q5 (partiel)** ⏳ — Déploiement VPS uniquement (`deploy_v9.py`/`v9_bootstrap.py`, crons).
  **`order_executor.py` (exécution réelle) explicitement hors périmètre** — reste gelé sous
  `AGENT.md` §Périmètre GELÉ jusqu'à confirmation explicite et distincte de l'utilisateur.

**Base avant série** : 1018 tests verts, 2 skips documentés — reconfirmé par run complet le
2026-07-12 avant tout changement.

## Clôturé — série de briefs O1→O5 + R (2026-07-12)

Tous les briefs techniques (O1-O5) sont **livrés et stagés** (commit-ready,
Hermes opérateur git unique — R28, pas encore commit/push). Brief R (ce
resync) en cours de clôture.

- **O1** ✅ — 8115 décisions TP_SL → DYNAMIC/SKIPPED (root cause : index
  manquant `decisions.decision_id`, corrigé). `principle_scores` régénérée
  (1ère fois en prod). Résolveur live basculé DYNAMIC + skip New York/After.
- **O2** ✅ — PrincipleScorer intégré dans `Arbiter.consolidate()` (pondération
  WR historique). Replay pré/post : WR admis par RiskManager 77.0% → 80.2%.
- **O3** ✅ — Branching HITL confiance 40-65 (informatif, `decision_logger.py`).
  Ne déroge pas à `CONFIANCE_MIN=70`.
- **O4** ✅ — Analyse biais New York/After (lecture seule). Recommandation :
  maintien du SKIP statu quo, décision Søn en attente.
- **O5** ✅ — Dataset V9-trader-mini exporté (préparation uniquement).
  Entraînement NON ouvert — GO séparé de Søn requis.
- **R** 🔄 — Resync workspace de continuité (ce fichier + BOARD.md +
  MEMORY_CANON.md + DOC_REGISTRY.yml).

**Tests** : 1018 verts, 0 régression sur l'ensemble de la série.

## Prochaines actions
1. **Hermes** — commit/push des livraisons O1→O5 (fichiers déjà stagés).
2. **Post-open marché** (dimanche 23h Paris = 21h UTC heure d'été) —
   vérifier que le résolveur live tourne bien en DYNAMIC + skip New York/After
   (corrigé Brief O1, propagé à `orchestrator.py` + daemon).
3. **Décisions Søn en attente** :
   - Recommandation O4 (SKIP maintenu / TP3-SL15 NY en SHADOW / filtre principe).
   - Dérogation HITL éventuelle sur le seuil `CONFIANCE_MIN=70` (aucune actée —
     le branching O3 reste strictement informatif).
   - GO entraînement V9-trader-mini (dataset prêt, non demandé à ce jour).
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
