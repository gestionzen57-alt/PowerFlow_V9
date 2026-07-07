# V9_PLAN_COMPLET — Plan détaillé de toutes les phases V9

> **Statut** : Document de référence. Mis à jour à chaque livraison de phase.
> **Audience** : Søn (CEO), Zcode, Claude Code, futurs agents.
> **Source de vérité** : `docs/ROADMAP.md` (séquencement) + `docs/DOCTRINE.md` (28 règles) + `docs/V9_FONCTIONNEMENT.md` (mode d'emploi) + checkpoints par phase.
> **Remplace** : aucune lecture d'un autre fichier ne doit contredire celui-ci sur le séquencement.
> **Dernière mise à jour** : 2026-07-07 14h30 CEST (post-Phase 9.9)

---

## 1. Vision d'ensemble

```
Phase 9.9 ✅ LIVRÉE (consolidation complète, dette = 0)
    ↓ (VPS reporté par Søn, observation pure)
Phase 9.10 — STABILISATION-LIVE (observation, WIN/LOSS collectés)
    ↓ (≥ 20 WIN/LOSS résolus, règle 25)
Phase 11 — LAYER MT5 (microstructure ticks)
    ↓ (Phase 11 stable 7j)
Phase 13 — APPRENTISSAGE + AUTO-CALIBRATION
    ↓ (WIN/LOSS ≥ 50 + modèles distillés)
Phase 10 — FÉDÉRATION D'AGENTS
    ↓ (VPS stable + Phases 9.10/11/13 matures)
Phase 12 — EXÉCUTION D'ORDRES (HITL obligatoire, interdit fondateur)
```

**Philosophie** : consolidation avant expansion (anti-V8 lesson, doctrine règle 22). Chaque phase produit 1 commit + DECISIONS_LOG + STATE.md à jour (règle 26). 0 régression test (règle 7). Périmètre strict : `core/v9/config.py`, YAML principes, `orchestrator.py` intouchés sauf dérogation explicite Søn.

---

## 2. Phases terminées (rappel)

| Phase | Livraison | Statut |
|---|---|---|
| 1 | Formats de données (6 fichiers JSON) | ✅ |
| 2 | Forces (EA MT4 + capture TCP + DB + stale gate) | ✅ |
| 3 | Scènes (`scene_builder.py`, coalitions/antagonismes) | ✅ |
| 4 | Comportements (`behavior_analyzer.py`, 12 qualifications) | ✅ |
| 5 | Fenêtres (`window_gate.py`, 6 statuts) | ✅ |
| 6 | Exploitabilité (`exploitability_evaluator.py`, 5 niveaux) | ✅ |
| 7 | Déploiement live (EA `ServerPort`, `market_calendar.py`, scripts) | ✅ |
| 8 | Monitoring (dashboard, calibration, replay — tous lecture seule) | ✅ |
| + | Orchestrateur live (chaîne automatique événementielle) | ✅ |
| 9 | Décision et Principes (Régime → Principes → Signal → Décision) | ✅ Canonisée 2026-07-05 |
| 9.7 | Paper-Trade Simulator (Arbiter + RiskManager + PaperTradeLogger) | ✅ 2026-07-07 |
| 9.8 | VPS-READY (heartbeat + 6 décisions §5 + rollback DNS swap) | ✅ 2026-07-07 |
| 9.9 | Consolidation Complète (C-1/C-2/C-3/C-4/C-5a/C-5b/3.3/F-3/F-4/F-5/F-6/F-7/F-8/F-9 + règle 28) | ✅ 2026-07-07 |

**Total** : 13 phases livrées, 588/588 tests verts, dette = 0, doctrine 28 règles.

---

## 3. Phase 9.10 — STABILISATION-LIVE (prochaine)

**Statut** : ⏳ À ouvrir (observation pure, 0 chantier code).
**Prérequis** : Phase 9.9 ✅, crons heartbeat installés.
**Décision Søn 2026-07-07** : VPS déploiement **reporté** (consolidation d'abord), Phase 9.10 = observation pure PC local.

### 3.1 Objectif
Observer le pipeline live 24/7, collecter ≥ 20 WIN/LOSS résolus, valider la stabilité avant Phase 11.

### 3.2 Livrables
1. **Crons heartbeat activés** : `scripts/install_heartbeat_cron.bat` en admin → 2 schtasks Windows (5min check + 60min alive Telegram).
2. **v9_daily_report.py quotidien 23h UTC** : rapport Telegram (signaux 24h, WIN/LOSS cumul, cohérence DB).
3. **Saisie WIN/LOSS manuelle** : `v9_resolve_decision.py --resolve <decision_id> --win|--loss --pips <N>`.
4. **v9_scoring.py** : hit_rate par principe (cumul 24h/7j/30j).
5. **v9_calibration.py --principes** hebdomadaire : propositions SHADOW→ACTIVE.
6. **Pipeline e2e observable** : `v9_dashboard.py --once` à la demande.

### 3.3 Conditions de succès (passage Phase 11)
- ≥ 20 WIN/LOSS résolus (règle 25 implicite)
- ≥ 1 trade gagnant (WR > 0%)
- Hit rate moyen ≥ 50% sur les 27 principes
- 0 régression test (règle 7 maintenue 588/588)
- Stabilité observée 7 jours minimum (heartbeat sans alerte critique)

### 3.4 Effort estimé
0 LOC, 0 test, 0 commit. Observation pure + saisie manuelle.

### 3.5 Risques
- WIN/LOSS = 0 (paper-trade jamais déclenché) → attendre 1-2 sessions London/NY
- WR < 40% → **STOP**, ne pas ouvrir Phase 11, recalibrer principes
- VPS down → bascule PC local via DNS swap (rollback 6a)

---

## 4. Phase 11 — LAYER MT5 (microstructure ticks)

**Statut** : ⏸️ Planifiée, conditionnelle WIN/LOSS ≥ 20 (Phase 9.10).
**Déblocage** : décision Søn explicite dans DECISIONS_LOG.md.

### 4.1 Objectif
Ajouter une couche 10 (entre Comportements et Fenêtres) qui ingère les ticks MT5 (vs bougies MT4). Améliore la précision temporelle des fenêtres de quelques minutes à quelques secondes.

### 4.2 Périmètre
- `core/v9/mt5_tick_reader.py` (~300 LOC) — listener TCP MT5 → SQLite
- `core/v9/mt5_tick_db.py` (~150 LOC) — table `mt5_ticks` (timestamp, bid, ask, volume, flags)
- `core/v9/tick_analyzer.py` (~250 LOC) — agrégations 1s/5s/10s, détection absorption/iceberg
- `core/v9/principle_engine.py` patch (règle 11 gel : ajouter 1-2 principes `kind=tick_rule`)
- `core/v9/_load_shared_context()` + `tick_metrics` (8 champs propagés)
- `scripts/v9_mt5_deploy.py` (~200 LOC) — install MT5 EA + cron local
- Tests : 4 fichiers (~50 tests)

### 4.3 Doctrine touchée
- **Règle 11** (principes gelés) : dérogation explicite Søn dans DECISIONS_LOG.md
- **Règle 14** (Git = vérité) : source de vérité schema = `core/v9/db_schema.py` (ajout table `mt5_ticks` dans `init_all_dbs()`)
- **Règle 18** (LLM non bloquant) : MT5 listener = code pur, pas de LLM
- **Règle 25** (SHADOW→ACTIVE) : les 2 nouveaux principes démarrent SHADOW

### 4.4 Effort estimé
~900 LOC + 50 tests + 1 doctrine amend = **3-4 commits** sur 1-2 semaines.

### 4.5 Conditions de succès
- 50/50 tests verts
- MT5 listener reçoit ticks sans drop (< 1% loss)
- 2 nouveaux principes ACTIVE routés correctement
- Pas de régression hit rate 27 principes existants

### 4.6 Risques
- MT5 broker VPS ≠ MT4 broker → tester latence avant
- Tick volume trop élevé → sampling 1s/5s (pas brut)
- 2 nouveaux principes = dette P2 à brancher → DORMANT si pas consommés

---

## 5. Phase 13 — APPRENTISSAGE + AUTO-CALIBRATION

**Statut** : ⏸️ Planifiée, conditionnelle WIN/LOSS ≥ 50 (Phase 9.10 prolongée).
**Déblocage** : décision Søn explicite dans DECISIONS_LOG.md.

### 5.1 Objectif
Permettre à V9 d'apprendre de ses trades résolus. 3 sous-chantiers :
1. **Auto-calibration des seuils** (Règle 25 SHADOW→ACTIVE automatisée)
2. **V9-trader-mini** (modèle local 4-12B distillé)
3. **Principe_builder** (HITL obligatoire pour nouveaux principes)

### 5.2 Sous-chantier 13.1 — Auto-calibration seuils (3-4 semaines)
- `core/v9/auto_calibrator.py` (~400 LOC) — recalibre COALITION/ANTAGONISM/PLIURE/SIMILARITY seuils depuis WIN/LOSS résolus
- `scripts/v9_auto_calibrate.py` (~200 LOC) — orchestrateur, HITL validation
- `docs/architecture/CONTEXT_CONTRACT.md` : seuils passent DORMANT → dynamiques
- Tests : 3 fichiers (~30 tests)

### 5.3 Sous-chantier 13.2 — V9-trader-mini (4-6 semaines)
Inspiration : vidéo YouTube `P51ebCFwnss` (distillation LLM via LM Studio, cf. `workspace/perplexity/inspiration/INSPIRATION_20260707_FABLE2.md`).
- `scripts/v9_export_traces.py` (~250 LOC) — export JSONL traces V9 (signals + decisions + WIN/LOSS)
- Fine-tuning Qwen 3.6 4B ou Gemma 4 4B sur dataset traces (~10K-50K samples)
- Quantization Q5_K_M (~3 GB final)
- Intégration LM Studio comme provider fallback (cf. FABLE 2 §3.2)
- `core/v9/mini_predictor.py` (~300 LOC) — interface Python vers le modèle
- Tests : 2 fichiers (~20 tests)

### 5.4 Sous-chantier 13.3 — Principe_builder (3-4 semaines)
- `core/v9/principe_builder.py` (~500 LOC) — propose nouveaux principes YAML depuis observations non couvertes
- `scripts/v9_principe_builder.py` (~200 LOC) — CLI avec HITL obligatoire
- **HITL** : chaque nouveau principe doit être validé Søn avant activation
- Tests : 2 fichiers (~20 tests)

### 5.5 Doctrine touchée
- **Règle 11** (principes gelés) : dérogation explicite 13.3
- **Règle 18** (LLM non bloquant) : V9-trader-mini = observateur uniquement
- **Règle 22** (chantier = livraison) : 13.1, 13.2, 13.3 = 3 sous-chantiers séparés, 3 commits
- **Règle 25** (SHADOW→ACTIVE) : 13.1 automatise partiellement (HITL conserve le dernier mot)
- **Règle 27** (DORMANT > 2 phases) : réévaluation des 6 P3 DORMANT

### 5.6 Effort estimé
~1850 LOC + 70 tests + 3 doctrine amends = **6-8 commits** sur 1-3 mois.

### 5.7 Conditions de succès
- 70/70 tests verts
- V9-trader-mini < 5% erreur vs V9 complet sur validation set
- Auto-calibration propose seuils qui **améliorent** hit rate (vs manuel)
- HITL fonctionne : 0 principe ajouté sans validation Søn

### 5.8 Risques
- V9-trader-mini trop petit pour apprendre → 8B ou 13B au lieu de 4B
- Fine-tuning consomme 4-8h GPU (PC Søn a RTX ?)
- HITL trop contraignant → 1-2 principes rejetés/jour max
- 6 P3 DORMANT non promus → règle 27 trigger, suppression

---

## 6. Phase 10 — FÉDÉRATION D'AGENTS (multi-analyse)

**Statut** : ⏸️ Planifiée, conditionnelle Phases 9.10/11/13 stables + WIN/LOSS ≥ 50.
**Déblocage** : décision Søn explicite dans DECISIONS_LOG.md.

### 6.1 Objectif
Multi-analyse parallèle. 6 agents cognitifs (1 par couche) + 1 orchestrateur + 1 reviewer HITL. Communication via bus événements SQLite.

### 6.2 Architecture cible
**Option B** (multi-agents asyncio), décidée post-Phase 11 (cf. `agents/AGENTIC_MAP.md` §5 décision §1). Justification : VPS 1 GB = trop juste pour Option C (RPC distribué), Option A (central Python) = pas de vrai parallélisme.

### 6.3 Périmètre
- `agents/orchestrator/` (squelette README → code ~500 LOC) — dispatch events
- `agents/scene-builder/` (~400 LOC) — agent Scènes autonome
- `agents/behavior-analyst/` (~400 LOC) — agent Comportements
- `agents/window-gate/` (~400 LOC) — agent Fenêtres
- `agents/exploitability-evaluator/` (~400 LOC) — agent Exploitabilité
- `agents/principle-engine/` (~400 LOC) — agent Principes (déjà `orchestrator.py`)
- `agents/reviewer/` (~600 LOC) — agent HITL, dialogue Telegram
- `core/v9/event_bus.py` (~300 LOC) — bus pub/sub SQLite
- `core/v9/agent_runtime.py` (~400 LOC) — lifecycle, restart, watchdog
- Tests : 8 fichiers (~80 tests)
- `agents/AGENTIC_MAP.md` MAJ : 3 options tranchées (cf. décision §5)

### 6.4 Doctrine touchée
- **Règle 18** (LLM non bloquant) : agents = code pur, LLM = observateur uniquement
- **Règle 22** (chantier = livraison) : 8 sous-chantiers séparés, 8 commits
- **Règle 11** (principes gelés) : agent Principes = lecture seule
- **Règle 28** (Hermes git unique) : orchestration V9 = Hermes, pas un agent

### 6.5 Effort estimé
~3800 LOC + 80 tests = **10-12 commits** sur 2-4 mois.

### 6.6 Conditions de succès
- 80/80 tests verts
- 6 agents tournent en parallèle sans deadlock
- Latence 9 couches < 200ms (cf. baseline Phase 9 : 189.58ms)
- HITL agent reviewer répond < 30s

### 6.7 Risques
- Asyncio + GIL sur 1 vCPU VPS = pas de gain → fallback Option A
- 6 agents = 6 sources de bugs → debug complexe
- Event bus SQLite = bottleneck si haut volume

---

## 7. Phase 12 — EXÉCUTION D'ORDRES (HITL obligatoire)

**Statut** : ⏸️ Interdit fondateur, **JAMAIS** ouverte sans décision Søn tracée dans DECISIONS_LOG.md.

### 7.1 Raison du gel
HITL obligatoire sur toute action destructrice (règle doctrine Phase 9). L'exécution d'ordres réels est le **dernier** chantier, après stabilisation prouvée.

### 7.2 Conditions de dégel (toutes obligatoires)
1. WIN/LOSS ≥ 100 résolus (vs 50 pour Phase 13)
2. Hit rate global > 55% sur 6 mois
3. Sharpe ratio > 1.0
4. Max drawdown < 15%
5. 6 mois d'observation live continue sans incident critique
6. Décision Søn explicite dans DECISIONS_LOG.md (pas de dégel tacite)

### 7.3 Périmètre (quand dégel)
- `core/v9/order_executor.py` (~600 LOC) — exécution MT4/MT5, retry, slippage tracking
- `core/v9/position_manager.py` (~500 LOC) — gestion positions ouvertes, stop-loss, take-profit
- `core/v9/risk_gate.py` (~400 LOC) — limites risque par trade, par jour, par semaine
- `core/v9/hitl_bridge.py` (~300 LOC) — Telegram review/approve/reject
- `scripts/v9_order_run.py` (~300 LOC) — orchestrateur
- Tests : 5 fichiers (~60 tests)
- Déploiement : broker API (MT4/MT5) → compte réel avec capital limité

---

## 8. Dépendances inter-phases (graph)

```
9.9 ✅ ──> 9.10 (observation live)
              │
              ├─ WIN/LOSS ≥ 20 ──> 11 (MT5)
              │                       │
              │                       └─ 11 stable 7j ──> 13 (apprentissage)
              │                                              │
              │                                              ├─ WIN/LOSS ≥ 50 ──┐
              │                                              │                  │
              └─ WIN/LOSS ≥ 50 ───────────────────────────────────────────┐      │
                                                                         │      │
                                                                         v      v
                                                                       10 (fédération)
                                                                         │
                                                                         └─ WIN/LOSS ≥ 100 + Sharpe > 1 + 6 mois stable ──> 12 (exécution)
```

**Gates WIN/LOSS explicites** :
- ≥ 20 : Phase 11
- ≥ 50 : Phase 13 + Phase 10 (en parallèle)
- ≥ 100 + Sharpe > 1 : Phase 12

---

## 9. Effort total estimé (post-9.9)

| Phase | LOC | Tests | Commits | Durée | Prérequis |
|---|---|---|---|---|---|
| 9.10 | 0 | 0 | 0 | 1-4 sem | VPS déployé (ou PC local si reporté) |
| 11 | ~900 | ~50 | 3-4 | 1-2 sem | WIN/LOSS ≥ 20 |
| 13.1 | ~600 | ~30 | 2 | 3-4 sem | WIN/LOSS ≥ 50 |
| 13.2 | ~750 | ~20 | 2 | 4-6 sem | 13.1 + traces V9 ≥ 10K |
| 13.3 | ~700 | ~20 | 2-3 | 3-4 sem | 13.1 + HITL Søn actif |
| 10 | ~3800 | ~80 | 10-12 | 2-4 mois | Phases 9.10/11/13 stables + WIN/LOSS ≥ 50 |
| 12 | ~2100 | ~60 | 5-7 | 1-2 mois | Phases 9.10/11/13/10 stables + WIN/LOSS ≥ 100 + Sharpe > 1 + 6 mois |
| **TOTAL** | **~8850** | **~260** | **24-31** | **6-12 mois** | séquentiel avec gates WIN/LOSS |

---

## 10. Règles d'or (à respecter à chaque phase)

1. **Règle 7** : 0 régression. Chaque phase ajoute des tests, ne casse aucun.
2. **Règle 14** : Git = vérité. Chaque phase produit 1 commit + DECISIONS_LOG + STATE.md à jour.
3. **Règle 22** : 1 livraison = 1 commit. Pas de chantier multi-phase dans 1 commit.
4. **Règle 25** : WIN/LOSS ≥ 50 pour SHADOW→ACTIVE. Pas de promotion sans preuve live.
5. **Règle 28** : Hermes gère le git. Søn valide le contenu, pas le contenant.

**Doctrine complète** : voir `docs/DOCTRINE.md` (28 règles immuables).

---

## 11. Prochaine action unique (Søn)

**Aujourd'hui** : Phase 9.9 close. Dette = 0. V9 en état canonique.

**Demain / cette semaine** : Phase 9.10 — observation live pure. Tu choisis :
- (a) Activer crons heartbeat (`install_heartbeat_cron.bat` en admin) → Telegram "alive" chaque 60 min
- (b) Laisser le pipeline tourner, saisir WIN/LOSS manuellement via `v9_resolve_decision.py` quand trade clos
- (c) Ouvrir un nouveau chantier non listé (urgence business)

**Recommandation** : option (b) — laisser vivre le système 1-2 semaines, accumuler des WIN/LOSS, puis décider Phase 11.

---

## 12. Références

- `docs/STATE.md` (état vivant, source de vérité)
- `docs/CACHE_BOARD.md` (reprise rapide 2 min)
- `docs/V9_FONCTIONNEMENT.md` (mode d'emploi global 12 sections)
- `docs/DOCTRINE.md` (28 règles immuables)
- `docs/ROADMAP.md` (séquencement 9-13)
- `docs/architecture/CONTEXT_CONTRACT.md` (contrat propagation)
- `docs/checkpoints/CHECKPOINT_2026-07-05_MEGA_V9.md` (mega-checkpoint Phase 9)
- `docs/checkpoints/CHECKPOINT_20260707_PHASE9_7.md` (Phase 9.7)
- `docs/checkpoints/CHECKPOINT_20260707_VPS_READY.md` (Phase 9.8)
- `docs/checkpoints/CHECKPOINT_20260707_PHASE9_9.md` (Phase 9.9)
- `agents/AGENTIC_MAP.md` (cartographie agentique)
- `workspace/perplexity/memory/DECISIONS_LOG.md` (journal décisions)
- `workspace/perplexity/JOURNAL.md` (deltas opérationnels)
- `workspace/perplexity/inspiration/INSPIRATION_20260707_FABLE*.md` (2 vidéos)
- `AGENT.md` (doc racine)
- `README.md` (entry point)
- Git : `git log --oneline -15` (15 commits session 2026-07-07)

---

**Plan complet V9 documenté. 6 phases restantes (9.10/11/13/10/12), 24-31 commits, 6-12 mois.**
**Phase 9.10 = prochaine, observation pure, WIN/LOSS collectés.**
**Phases 10/12 conditionnelles à WIN/LOSS + Sharpe + 6 mois stables.**

═══════════════════════════════════════════════════════════════
FIN DU PLAN
═══════════════════════════════════════════════════════════════