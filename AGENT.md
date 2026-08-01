# AGENT.md — PowerFlow V9

## Statut
Document racine du système PowerFlow V9. **Niveau quantique institutionnel** — Phase 9.9 + 9.10-RULE29 + Sprint Søn Mode A + Q1→Q5 + Autopilot CEO + ORDER-BRIDGE + P2 shadow + P3-CONSUME-EXTEND + Mandat CEO boucle fermée + DIVERSIFY A+B+C + DRM APPLY + 6 paires live + USDCAD blacklisté + **5 leviers quantiques** (PortfolioRiskManager câblé + walk-forward + position manager + risk-on/off + rapport quotidien). 30 règles doctrine (R20' lecture-first, R25'' auto-promotion, R28 git multi-agent, R29 lecture multi-TF, R30 boucle fermée, R31 vérification vocabulaire, R32 cycles/phases).

## État système — généré automatiquement

<!-- AUTO:STATE -->
<!-- Généré automatiquement par scripts/v9_sync_state.py — 2026-07-31 14:21 UTC -->
<!-- Ne pas éditer manuellement. Pour forcer : python scripts/v9_sync_state.py -->

| Métrique | Valeur | Source |
|---|---|---|
| HEAD | `5b54061 feat(v9): Phase 19 motion CEO « EDGE FUND MAX » — token rotation + mirror auto-activate` | `git log --oneline -1` |
| Tests collectés | 3001 | `pytest --collect-only` |
| Tables DB | 27 | `sqlite3 data/v9_forces.db` |
| Index DB | 64 | `sqlite3` |
| Taille DB | 6.30 GB | `du -h` |
| Décisions | 104140 | `SELECT count(*) FROM decisions` |
| Forces snapshots | 239207 | DB |
| Scènes | 35344 | DB |
| Principle evals | 8020085 | DB |
| Régime snapshots | 276696 | DB |
| Paper trades | 337 | DB |
| Principle scores | 575 | DB |
| Principes YAML | 56 (39 ACTIVE + 17 SHADOW) | `ls core/v9/principles/*.yaml` |
| Serveurs MCP | 16 | `ls mcp_servers/*.py` |
| Crons Ready | 38 | `Get-ScheduledTask (PowerShell)` |
| V9_TRADER_MINI_ENABLED | 0 | `config/v9_kill_switches.env` |
| V9_AUTO_CALIBRATOR_ENABLED | 1 | env |
| V9_SHADOW_MODE_ENABLED | 0 | env |
| V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED | 1 | env |
| V9_EXECUTION_ENABLED | 1 | env |
| V9_LEARNING_OFFSET_ENABLED | 1 | env |
| V9_DYNAMIC_RISK_ENABLED | 1 | env |
| V9_BLACKLIST_SYMBOLS | USDCAD,AUDUSD,USDJPY,EURUSD,USDCHF | env |
| V9_GBPUSD_LONG_ONLY | 0 | env (activé 2026-07-18 §6.10) |
| V9_BEAR_PERCEPTION_ENABLED | 0 | env (shadow) |
| V9_CONSTITUTIVE_CURRENCY_FILTER | 0 (défaut OFF, R22) | env (shadow) |
| V9_CYCLE_MEMORY_ENABLED | 1 | env (Phase E, R33) |
| V9_META_STRATEGY_OPTIMIZER_ENABLED | 1 | env (Phase E) |
| V9_BAYESIAN_PREDICTOR_ENABLED | 1 | env (Phase E) |
| V9_PREDICTIVE_ENGINE_ENABLED | 1 | env (Phase E) |
| V9_LEARN_LOOP_ENABLED | 1 | env (Phase E) |

<!-- /AUTO:STATE -->

## Mission
PowerFlow V9 est un système de lecture comportementale des forces de marché.
Il observe, structure, mémorise, confronte et qualifie les dynamiques de marché
avant toute logique d'exploitabilité ou d'exécution.

## Priorité absolue
1. Fidélité de lecture
2. Cohérence comportementale
3. Mémoire et confrontation replay
4. Qualification des fenêtres
5. Exploitabilité
6. Exécution éventuelle (gelée par doctrine jusqu'à Phase 12)

## Phrase directrice
Ne jamais demander au système de trader ce qu'il ne sait pas encore décrire.

## Architecture MCP (15 serveurs — 14 actifs + 1 helper runtime)

15 fichiers dans `mcp_servers/`, 14 register dans `.mcp.json` (projet) + 1 helper
runtime (`stdio_runtime.py` — compatibilité stdio MCP standard + protocole legacy Hermes, non register car helper interne) :

| Serveur | Fichier | Rôle | Appelé en prod |
|---|---|---|---|
| doctrine | `doctrine_server.py` | Lit DOCTRINE.md, règles assouplies | ❌ Tests seulement |
| filesystem | `filesystem_server.py` | Lecture/écriture fichiers V9 | ❌ Tests seulement |
| meta_agent | `meta_agent_server.py` | Bus agent + propositions | ❌ Tests seulement |
| p3_consume | `p3_consume_server.py` | Stats principes, shadow principles | ❌ Tests seulement |
| pipeline | `pipeline_server.py` | Start/stop pipeline, run scripts whitelist | ❌ Tests seulement |
| sqlite | `sqlite_server.py` | Requêtes SQL sur data/v9_forces.db | ❌ Tests seulement |
| telegram | `telegram_server.py` | Envoi notifications Telegram | ✅ 3 scripts production |
| paper_trade | `paper_trade_server.py` | Lecture paper_trades (read-only strict) | ❌ Tests |
| meta_strategy_shadow | `meta_strategy_shadow_server.py` | Logs Phase E (read-only) | ❌ Tests |
| data_integrity | `data_integrity_server.py` | Audit intégrité DB | ❌ Tests |
| edge_decay | `edge_decay_server.py` | EdgeDecayMonitor (motion CEO 28/07) | ❌ Tests |
| risk_dashboard | `risk_dashboard_server.py` | 3 modules risque temps réel (HITL CEO) | ❌ Tests |
| meta_agent_bus | `meta_agent_bus_server.py` | Bus agent V9 (Phase 10 infra) | ❌ Tests |
| walk_forward | `walk_forward_server.py` | Validation walk-forward OOS (CEO self-service) | ❌ Tests |
| strategy_pole | `strategy_pole_server.py` | Pôle stratégie (12 tools : meta, catalogue, top, worst, recommend, tune, save_catalogue, hedge_fund_summary, live_snapshot, pair_breakdown, principle_leaderboard, dashboard_summary) | ❌ Tests (livré 2026-07-18, ROADMAP §Phase BCD) |

**Note** : 14/15 serveurs ne sont appelés que par les tests. Le register `.mcp.json`
permet aux clients MCP (Claude, ZCode) de les découvrir. Les scripts production
appelent directement les modules `core/v9/*.py` sans passer par MCP.

**Resync 2026-07-31** : 8 serveurs actifs non listés ajoutés (paper_trade, meta_strategy_shadow,
data_integrity, edge_decay, risk_dashboard, meta_agent_bus, walk_forward + strategy_pole).
Cf. DECISIONS_LOG §Resync MCP+skills 2026-07-31.

## État courant — Niveau quantique institutionnel (2026-07-18)

- **Branche** : `feat/v9-foundation-clean` (up-to-date avec origin)
- **HEAD** : `6294539` — 5 leviers quantiques (PRM + walk-forward + position manager + risk-on/off + rapport)
- **Tests** : **1795 passed, 6 failed (pré-existants), 1 skipped** (1802 collectés)
- **Guards** : 6/6 verts (no-secrets, yaml-sync, scripts-exist, hitl-sync, db-sync, kill-switch-integrity)
- **Chaîne cognitive** : 9+1 couches + boucle fermée + SignalFusionEngine + DynamicRiskManager + PortfolioRiskManager
- **Principes** : **46 ACTIVE + 9 SHADOW** = 55 YAML
- **6 paires live** : GBPUSD, USDJPY, USDCHF, EURUSD, AUDUSD + USDCAD (blacklisté)
- **MT4 SDI** (pas de MT4) — port 31685
- **Crons Windows** : 14/14 Ready + V9CaptureWatchdog Running

### 5 leviers quantiques institutionnels (2026-07-18)

| Levier | Module | Kill switch | Défaut | Rôle |
|---|---|---|---|---|
| **P0 Survie** | `portfolio_risk_manager.py` câblé dans `trade_engine.py` | `V9_PORTFOLIO_RISK_ENABLED` | **ON** | Corrélation, net exposure, circuit breaker, DD 24h |
| **P1 Confiance** | `walk_forward.py` + `scripts/v9_walk_forward.py` | — | — | Validation edge sur 5 fenêtres anchored |
| **P2 Performance** | `position_manager.py` | `V9_POSITION_MANAGER_ENABLED` | **OFF** | Break-even 30%, partial close 50%, time-exit |
| **P3 Contexte** | `market_regime_global.py` | `V9_MARKET_REGIME_GLOBAL_ENABLED` | **OFF** | USD strength + risk-on/off injecté dans DRM |
| **P4 Transparence** | `scripts/v9_daily_report.py` | — | — | P&L veille, WR par dimension, edge decay, Telegram |

### Modules institutionnels complets

| Module | Rôle | Statut |
|---|---|---|
| `dynamic_risk_manager.py` | SL/TP adaptatifs par phase (cycles) | ✅ APPLY |
| `portfolio_risk_manager.py` | Risk portfolio (corrélation, exposure, circuit breaker) | ✅ Câblé ON |
| `transaction_costs.py` | Coûts réels (spread + commission + slippage) | ✅ Intégré |
| `edge_validator.py` | Validation statistique (p-value, IC 95%, Sharpe) | ✅ Intégré |
| `auto_calibrator.py` | Boucle fermée writable (seuils, promotions) | ✅ Actif |
| `auto_optimizer.py` | Grid search 81 TP×SL tous les 50 trades | ✅ Actif |
| `signal_fusion_engine.py` | Fusion principes faibles → signaux forts | ✅ Actif |
| `walk_forward.py` | Walk-forward validation 5 fenêtres | ✅ Livré |
| `position_manager.py` | Gestion positions multi-temps | ⏸️ OFF (décision CEO) |
| `market_regime_global.py` | Risk-on/risk-off detector | ⏸️ OFF (décision CEO) |

### Seuils calibrés (config.py)
| Seuil | Valeur | Statut | Base |
|-------|--------|--------|------|
| `ANTAGONISM_THRESHOLD` | 31.39 | **CALIBRÉ** (P80, n=218 M5+ live) | commit `460716f` |
| `COALITION_THRESHOLD` | 5.38 | calibré (config.py) | OK |
| `PLIURE_THRESHOLD` | 1.7 | **CALIBRÉ** (P90 pente réelle, n=1454 M5+) | commit `e9bd9b1` |
| `REGIME_LOOKBACK_BARS` | 20 | PORTÉ V8 (non recalibré) | P3 |
| `SIMILARITY_THRESHOLD` | 0.65 | PORTÉ V8 (non recalibré) | P3 |
| `REPLAY_MIN_CAS` | 3 | MALUS live naissant | P3 → temp 1 recommandé |

### Règles doctrine applicables (DOCTRINE.md)
- **Règle 20'** : Lecture-first — avant tout chantier de code sur marché ouvert, l'opérateur LIT d'abord l'état courant (`v9_calibration.py --analyze`, `v9_dashboard.py --once`). Remplace R20 (Calibration-first, supprimée pour contradiction CHARTE Interdit #4).
- **Règle 21** : Toute métrique ajoutée → tracée dans `CONTEXT_CONTRACT.md` (PROPAGÉ/DORMANT justifié)
- **Règle 22** : Une session = un périmètre = une livraison complète (assoupli 2026-07-14, DOCTRINE.md §R22 — sauf chantier complexe découpé en sous-unités)
- **Règle 23** : Principes YAML consommateurs mis à jour même session que le champ contexte
- **Règle 25'** : Vocabulaire descriptif — promotion SHADOW→ACTIVE conditionnée à la maturité structurelle (conditions écrites + champs PROPAGÉS + décision Søn tracée), sauf mandat CEO explicite contraire — jamais à un hit_rate arbitraire. Remplace R25 (hit_rate ≥ 60%, supprimée pour contradiction CHARTE Interdit #4).
- **Règle 27** : Champ DORMANT > 2 phases → réévaluation (PROPAGÉ ou maintenu avec justification)

### Calibration --principles (n=3306 évaluations)
| Principe | Statut | Hit Rate | Déclenchements | Promouvable ? |
|----------|--------|----------|----------------|---------------|
| POWER_ANGLE_BREAK | ACTIVE | 1.1% | 38 | ❌ |
| PRICE_LAG_AT_NODE_BIRTH | ACTIVE | 3.6% | 120 | ❌ |
| ZONE_RETEST | ACTIVE | 1.6% | 54 | ❌ |
| COALITION_NODE | ACTIVE | 1.5% | 48 | ❌ |
| NODE_BIRTH_FAST | ACTIVE | 0.6% | 20 | ❌ |
| RAW_NODE_BIRTH | ACTIVE | 0.6% | 20 | ❌ |
| GRAVITY_RESPRING_NODE | ACTIVE | 0.4% | 13 | ❌ |
| ANTAGONIST_NODE | ACTIVE | 0.0% | 0 | ❌ (aligné H1/M5) |
| ELASTIC_BREATH | ACTIVE | 0.0% | 0 | ❌ |

**Verdict** : Promotion SHADOW→ACTIVE conditionnée à la maturité structurelle (R25' — conditions écrites + champs PROPAGÉS + décision Søn tracée), pas à un hit_rate arbitraire. Les motions CEO successives constituent des mandats explicites couvrant un périmètre autorisé de promotions.

## Ordre cognitif officiel
1. Forces
2. Scènes
3. Comportements
4. Fenêtres
5. Exploitabilité
6. Exécution éventuelle

## Interdits
- Ne pas sauter directement vers signal / trade / optimisation.
- Ne pas remplacer la perception par une logique de scoring prématurée.
- Ne pas introduire un outil ou une architecture sans préciser sa place dans la chaîne cognitive.
- Ne pas hériter implicitement de V8, Hermes legacy, Bash legacy ou workflows non audités.
- Ne pas confondre mémoire de lecture et mémoire d'exécution.

## Entrées principales
- Forces multi-devises MT4/SDI (port 31685)
- Structure multi-timeframe (M5, M15, M30, H1, H4, D1)
- Tick lecture complémentaire MT4
- Zones (`zone_diagnostics` alimentée par `ZoneDetector`)
- Fenêtres
- Historique de scènes
- Mémoire comportementale
- Replay validé (`source_type` live/replay sur 8 tables)

## Sorties principales
- Lecture structurée de forces
- Scène courante (coalitions, antagonismes, cinématique, confluences MTF, risk assessment)
- Comportement qualifié (avec similarité historique + bonus confiance)
- Statut de fenêtre (ouverte/absente/préparation/invalidée/fragile)
- Niveau d'exploitabilité (exploitable/non_exploitable + confiance globale)
- Décision (preparer_entree / surveiller / observer / aucune_action) + confiance
- Rapport synthétique
- Mise à jour mémoire (principle_evaluations, decisions idempotentes)

## Routing conceptuel
### Si la tâche concerne la perception
router vers :
- force-reader (`core/v9/forces_reader.py`)
- scene-builder (`core/v9/scene_builder.py`)
- behavior-analyst (`core/v9/behavior_analyzer.py`)

### Si la tâche concerne la confrontation
router vers :
- replay-confronter (`scripts/regenerate_chain.py --replace-derived`)
- reviewer (`scripts/v9_calibration.py --principes`)

### Si la tâche concerne la qualification
router vers :
- window-gate (`core/v9/window_gate.py`)
- exploitability-gate (`core/v9/exploitability_evaluator.py`)

### Si la tâche concerne la doctrine
router vers :
- doctrine-keeper (`docs/DOCTRINE.md` + `docs/doctrine/*.md`)

## Conditions d'arrêt
Le système s'arrête si :
- la lecture est incomplète
- la scène est ambiguë
- le comportement n'est pas qualifiable
- la fenêtre n'est pas confirmée
- une validation humaine est requise
- un garde-fou est atteint

## Validation humaine obligatoire
Demander HITL si :
- ambiguïté élevée
- comportement nouveau ou contradictoire
- fenêtre sensible
- action irréversible
- conflit entre couches cognitives
- doute sur la fidélité de lecture

## Garde-fous
- max itérations
- stagnation
- budget temps / coût / tokens
- rollback logique
- refus d'exécution si perception non stabilisée

## Chantiers en file (ordre de priorité)
1. **Observation live continue** — sessions Asie/Europe/US, relancer `--principes` matin/aprèm
2. **Calibration `--principes` à ~500 scènes** post-tuning YAML (news-aware session 4 + P2 DORMANT session 5)
3. **COALITION_THRESHOLD** — calibré à 5.38 (config.py), réévaluer si WIN/LOSS montre un palier différent
4. **Promotion SHADOW→ACTIVE** — décision sur hit_rate live (règle 25)
5. **AGENT.md** racine V9 — ✅ CE DOCUMENT
6. **Inventaire migration V8→V9** — audit selon `MIGRATION_POLICY_V9.md`

## Périmètre GELÉ (ne jamais ouvrir)
- Phase 10 : Fédération d'agents
- Skills auto-générés / briques / agents spécialisés
- Architecture globale agents / routing modèles / mémoire avancée
- Exécution d'ordres réelle avant phase prévue par doctrine

## Commandes de vérification rapide
```bash
# Calibration seuils + principes
python scripts/v9_calibration.py --analyze
python scripts/v9_calibration.py --principes

# Dashboard live
python scripts/v9_dashboard.py --watch decisions --once
python scripts/v9_dashboard.py --watch signals --once

# Tests
python -m pytest tests/ -q
```

## Multi-IA & Git operator (R28 — procédure 2026-07-09)

PowerFlow V9 collabore avec **4 IA + 1 humain** (Søn CEO). Coordination :

| Acteur | Rôle | Code ? | Git direct ? |
|--------|------|--------|--------------|
| **Søn** | CEO, lectures marché, HITL final | Non | Non |
| **Hermes** | Orchestrateur H24, **opérateur git unique** (R28 assouplie 14/07 : délégation possible sur motion CEO explicite) | Oui | **OUI (seul)** |
| **Perplexity** | Doctrine, orchestration, structure | Non | Non |
| **Claude Code** | Implémentation assistée | Oui (assisté) | Non (via Hermes) |
| **Zcode** (deepseek-v4-flash / Ollama Cloud) | Implémentation assistée | Oui (assisté) | Non (via Hermes) |

**Procédures complètes** :
- **`docs/GIT_OPERATOR_PROCEDURE.md`** — qui commit/push, comment, quand (auth, branches, recovery)
- **`docs/MULTI_IA_PROCEDURE.md`** — coordination inter-IA, worktrees, handoffs, sécurité secrets

**Règle d'or** : aucune IA (Claude, Zcode) ne tape de commande git. Tout passe par Hermes.

## Références pivots
- `docs/DOCTRINE.md` (index des 30 règles immuables)
- `docs/GIT_OPERATOR_PROCEDURE.md` (procédure git + auth PAT)
- `docs/MULTI_IA_PROCEDURE.md` (coordination 4-IA + rôles)
- `docs/doctrine/CHARTE_COGNITIVE_V9.md`
- `docs/doctrine/MEMORY_POLICY_V9.md`
- `docs/doctrine/ORCHESTRATION_POLICY_V9.md`
- `docs/doctrine/MIGRATION_POLICY_V9.md`
- `docs/LEXIQUE.md` → `docs/lexicon/LEXICON_V9.md`
- `docs/ARCHITECTURE.md`
- `docs/NOMENCLATURE.md`
- `docs/ROADMAP.md` (V2 opérationnelle — 6 axes post-audit edgefund 19/07)
- `docs/DOC_GOVERNANCE.md`
- `docs/STATE.md` (détail vivant par phase)
- `docs/CACHE_BOARD.md` (tableau de reprise compact)
- `memory/memory.md` (**mémoire persistante unifiée** — tous agents IA)
- `memory/exchange.md` (**bus de coordination inter-agents** — handoffs, demandes CEO, statuts)
- `workspace/perplexity/memory/DECISIONS_LOG.md`
- `workspace/perplexity/MEMORY_CANON.md` (faits gravés infrastructure)
- `workspace/perplexity/ACTIVE_TASKS.md`
- `docs/architecture/CONTEXT_CONTRACT.md` (contrat propagation inter-couches)
- `docs/deployment/V9_AUTOMATION_RUNBOOK.md` (reboot/ouverture marché/reprise session)

## Rituel de démarrage session (ordre obligatoire)
0. Lire `memory/exchange.md` (handoffs inter-agents + demandes CEO en attente)
1. `git pull` + `pytest tests/ -q` → confirmer base saine
2. [Marché ouvert ?] OUI → `python scripts/v9_calibration.py --analyze` OBLIGATOIRE
3. Périmètre explicité : un chantier, une livraison complète (R22 assouplie 14/07 : sous-unités livrables autorisées pour chantiers complexes)
4. Implémentation
5. Tests verts (zéro régression non justifiée — règle 7, assoupli 2026-07-14)
6. `CONTEXT_CONTRACT.md` mis à jour si nouveau champ
7. Principes YAML consommateurs mis à jour (règle 23)
8. Commits atomiques (1 par unité logique)
8. DECISIONS_LOG.md — 1 entrée par décision structurante
9. STATE.md à jour
10. `memory/memory.md` à jour (mémoire persistante unifiée)
11. `memory/exchange.md` à jour (statut agent + handoffs)
12. `git push`