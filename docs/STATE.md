# STATE — PowerFlow V10

**Pointeur exécutif actif — mis à jour :** 2026-08-06 12:32 CEST
**Branche / HEAD :** `feat/v9-foundation-clean` / `23cf024b8cd3d21be2ec7266532476c217f6ef28`
**Validation courante :** `python -m pytest tests/test_v10_*.py -q` → **1239 passed**, 3 warnings `sklearn` attendus.

> Le détail canonique est `docs/V10/STATE.md`; la gouvernance de fraîcheur documentaire est dans `docs/V10/DOCUMENT_STATUS.md`. Le contenu V9 historique ci-dessous est conservé comme contexte, pas comme état live.

---

## État actif consolidé

- Cognitive Continuum livré : pont mémoire V9 read-only, registre `v10_behaviors`, Cortex, apprentissage, RAG sur mémoire propre et audit d’auto-cohérence.
- Auto-cohérence documentée : 17 modules de lecture connectés, 0 orphelin.
- Audit R9 : stale gate dans les deux boucles live; WR calculé uniquement sur les outcomes résolus; cohérence/drift filtrés sur M30/H1/H4.
- Phase 12 clôturée : contexte fractal 7 TF + cinématique M1/M5, structure S1-S9 dans la décision live, garde SELL data-driven.
- Posture d’exécution : V10 signal/paper/shadow; aucun ordre réel V10 vérifié. `V9_EXECUTION_ENABLED=1` est un résidu V9 à ne pas confondre avec une capacité d’exécution V10.

## Historique V9/V10 antérieur

### Stack quant libérée (doctrine CEO no-limit)
- `pyproject.toml` v0.10.0 : scipy, statsmodels, sklearn, hmmlearn, ruptures,
  arch, plotly, finta — **tous installés et vérifiés** dans le venv des tests.
- R10 inchangé : **zéro ordre réel** — 0 occurrence `order_send` dans core/v10/
  et scripts/v10_*.py (vérifié exhaustivement). Paper-trader hard-codé
  paper_only=True, MT5 bridge lecture seule.

### Bug critique RÉPARÉ (audit R9) — commit `885a851`
- **Safe Haven flip inversé** : `v10_currency_strength._compute_raw_returns`
  inversait le signe des paires inversées (USDJPY/USDCHF/USDCAD). Quand
  JPY/CHF s'apprécient, le moteur les classait "faibles" et USD "fort" —
  l'inverse de la réalité de marché. Impact : filtre Safe Haven (Principe 3
  Fatboy) et rankings devises inversés en production.
- Fix : `returns[quote] = raw` (la quote suit son propre retour), `USD -= raw`.
- Validé : JPY=100/CHF=100/USD=4.6 sur scénario safe_haven (était l'inverse).
- **Dette R9 (1 test safe_haven pré-existant) RÉPARÉE** — 96 tests
  currency_strength verts.

### Réconciliation doublon (mandat "zéro dette")
- `v10_strategy_layers` (ZCode) réécrit en **wrapper** de
  `v10_filter_compositor.compose_filters` (Hermes Sprint 4) — cœur de filtrage
  UNIQUE (session + ICT OTE + SMC + regime), plus de duplication.
- Export package `core/v10/__init__.py` vérifié : **zéro nom non résolu**
  dans `__all__` (27 noms étaient déclarés sans import — réparé).

### Pipeline live branché (Sprints Hermes 1-15)
- **Sprint 15** : cron boucle décision live 30min (BUY/SELL/WAIT persistés)
- **Sprint 14** : `v10_live_decision.py` — polling bars live → régimes HMM →
  décision (EURUSD/CHF/AUD SELL, GBPUSD BUY, USDJPY/CAD WAIT)
- **Sprint 13** : `v10_decision_pipeline.py` — decide_entry + bouclier R10
- **Sprint 12** : démo composition publique live (OTE+SMC+HMM+Wyckoff)
- **Sprint 11** : risk dashboard R10 (net exposure par devise)
- **Sprint 10** : `v10_risk_shield.py` — gates R10 unifiés (DD halt, position
  max 2%, doubles opposées, corrélation)
- **Sprint 9** : `v10_net_exposure.py` — exposition nette + doubles opposées
- **Sprint 8** : cron nocturne auto (night_report + closed_loop + shadow)
- **Sprint 7** : `v10_auto_recalibrator.py` — boucle R8 (drift → REVERT
  conservateur : after_wr=0 < before_wr=0.49)
- **Sprint 6** : night report + shadow promotion — **verdict HOLD** (1/4 gates)
- **Sprint 5** : gate final public_filters dans orchestrateur + error learner
- **Sprint 4** : filter_compositor + GARCH vol + Wyckoff consolidé
- **Sprint 2-3** : HMM régimes + SMC public + ICT OTE

### Capture & infra
| Élément | État |
|---|---|
| Capture server | ✅ port 31685 LISTENING |
| DB v9_forces.db | ✅ 259 540+ snapshots, fraîcheur ~1 min |
| Orchestrateur | 2 workers alive, 0 crash |
| MT5 bridge | ✅ Tickmill (paper-only) |
| V9_EXECUTION_ENABLED | ⚠️ =1 dans config (résidu V9 non consommé par V10 — documenté R9) |

---

## ⚠️ Dettes restantes (R9 honnête)

1. **15 tests V9 échouent** en suite complète (pré-existants, modules V9
   verrouillés, hors périmètre V10) — liste :
   - `test_v9_trade_engine_long_only` (3), `test_v9_principle_alert` (3),
     `test_v9_edge_alert` (2), `test_v9_learning_loop` (2),
     `test_v9_audit_v2`, `test_v9_oos_freeze_test`, `test_v9_phase146_audit_live`,
     `test_arbiter`, `test_install_v9_signal_alerter_task`
2. `V9_EXECUTION_ENABLED=1` dans `config/v9_kill_switches.env` — résidu V9 ;
   aucun consommateur V10 ne l'utilise (0 order_send), mais à nettoyer côté V9
3. `docs/V10/CACHE_BOARD.md` obsolète (692 tests, HEAD 40ed93a) — Hermes le
   maintient en parallèle

---

## 🔄 Prochaines étapes

1. **Calibration live Fatman** (Phase A) : comparer sortie FatmanCalculator vs
   lecture visuelle indicateur (critère 10 signaux alignés)
2. **Promotion RL SHADOW→ACTIVE** : 100 trades paper, cible Sharpe ≥ 0.5
   (gates R10 : WR≥50, Sharpe≥0.3, DD≤50p, consistency≥75%)
3. Valider durablement les signaux live (Sprint 14-15) sur 2-3 jours
4. Nettoyer les 15 tests V9 rouges (chantier V9 verrouillé, mandat Søn requis)

## Compteur tests
**1172/1172 tests V10 verts** (vérifié 2026-08-05 17:50 UTC)
Suite complète : 5421 passed / 16 failed (15 V9 pré-existants + 0 V10)

## Liens
- `docs/V10/STATE.md` — détail des Sprints 1-15 (Hermes)
- `workspace/perplexity/memory/DECISIONS_LOG.md` — décisions structurantes
- `docs/V10/V10_QUANT_UPGRADE_SPRINT23.md` — rapport QUANT UPGRADE
