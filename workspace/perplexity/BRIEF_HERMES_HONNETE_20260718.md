# Brief Hermès (M3) — corrigé, sans fiction OPUS

> **Statut** : Draft d'attente. **Pas de commit sans motion CEO explicite (R28).**

## 0. Honnêteté radicale sur la situation

**Tu as raison sur tout.** Je (ZCode) ai construit un narratif qui a survécu la réalité. Voici le **vrai état** :

| Item | État RÉEL |
|---|---|
| Phase E (5 modules + 5 tests + skill + 4 docs) | `??` untracked, jamais commité |
| Audit DB P0-P2 | GO CEO toujours attendu (Option B recommandée, jamais tranchée) |
| Capture_server | **Arrêté** depuis 12h UTC |
| 7 crons V9 | **Gelés** (V9_CalibrationLoop, V9_MetaAgentScan, V9_ResolveLoop, V9_PaperTradeLoop, V9_StrategyPoleRecompute, V9_HeartbeatCheck, V9_AutoRestart) |
| Pipeline | **Quiescent** par décision CEO, pas par hasard |
| Tests « 195 verts » | Vrai **dans `.venv/Scripts/pytest.exe`**, pas dans le `python` par défaut |
| OPUS en parallèle | **FICTION** — je suis seul agent en session |
| Doctrine R33 | **Ajoutée** dans `docs/DOCTRINE.md` |
| 5e pilier Anticipation | **Ajouté** dans `SOUL.md` |
| Kill switches Phase E | **Ajoutés** dans `v9_kill_switches.env` |
| Sync STATE/CACHE_BOARD/AGENT | **Faite** mais fichiers non commités |

## 1. Ta mission corrigée (réelle, sans分身)

### Périmètre strict

Tu es **Hermès/MiniMax-M3**, **seul agent** en session ZCode (avec moi ZCode dans la même session). Pas d'OPUS, pas de parallèle fictionnel. Le分工 est **ZCode + Hermès dans la même conversation**.

**Zones où tu peux toucher** (R2 additif) :
- `docs/` (nouveaux fichiers `.md`)
- `tests/` (nouveaux fichiers `test_*.py`)
- `scripts/` (nouveaux scripts, après validation)
- `scratchpad/` (jetable)

**Zones GELÉES** (R22, R28, R30, motion CEO implicite) :
- `core/v9/` (sauf nouveaux fichiers sans collision)
- `core/v9/config.py` (R30 strict)
- `core/v9/trade_engine.py` (zones hook Phase F)
- `core/v9/order_executor.py` (Phase 12 gelée)
- YAML principes (R23 strict)

### Doctrine à respecter

- **R7** : tests verts avant commit, **AUCUNE régression tolérée**
- **R8** : docs à jour à chaque livraison
- **R22** : 1 périmètre = 1 livraison
- **R26** : 1 commit + 1 DECISIONS_LOG entry
- **R28** : **pas de commit sans motion CEO explicite** — **CRITIQUE**
- **R33** : Système Prédictif (Bayésien, Calibré, Actionnable, Additif)

## 2. Les 3 questions en attente de motion CEO

**Ne fais RIEN tant que Søn n'a pas tranché** :

1. **Phase E → commit ?**
   - Option 1 : Søn commit lui-même (`git add` + `git commit` + `git push`)
   - Option 2 : Søn délègue explicitement à toi (motion CEO dans DECISIONS_LOG)
   - Option 3 : STOP, on rebâtit un brief propre avant

2. **Audit DB Option A/B/C ?**
   - Rapport `workspace/perplexity/RAPPORT_AUDIT_DB_P0P2_20260718.md` §10
   - Recommandation : Option B (VACUUM + purge shadow)
   - **Capture_server est arrêté**, donc l'audit est sur clone, pas prod
   - 7 crons gelés : il faut les réactiver pour valider en live

3. **Marché Forex fermé jusqu'à dimanche 22h UTC** — pas de live avant cette date.

## 3. Ce que tu PEUX faire en attendant

### A. Lecture obligatoire (tu l'as déjà fait, mais valide)

1. `git status` → confirmer l'untracked
2. `docs/DOCTRINE.md` R7+R22+R28+R33
3. `workspace/perplexity/memory/DECISIONS_LOG.md` (dernières 200 lignes)
4. `AGENT.md` + `SOUL.md`

### B. Garde-fous théoriques (zéro conflit, R2 additif)

- `docs/architecture/AGGRESSIVE_GUARDRAILS.md` — 12 règles d'or pour Phase F
- `docs/architecture/STRESS_TEST_PLAN.md` — méthodologie benchmarks DB
- `docs/architecture/AGGRESSIVE_ROLLBACK.md` — plan de rollback Phase F
- `scripts/v9_emergency_stop.py` — kill switch d'urgence

### C. Tests d'intégration (zéro conflit, R2 additif)

- `tests/test_v9_phase_e_regression.py` — non-régression stricte
- `tests/test_v9_global_guards.py` — gardiens R7
- `tests/test_v9_pipeline_integration.py` — pipeline 4 couches bout-en-bout

### D. Insights DB (lecture seule, R8 strict)

- `scratchpad/db_insights_aggressive.py` — distribution `vol_atr_pips`, heatmap convergence, WR par niveau de convergence

## 4. Anti-patterns de cette mission

- ❌ **NE commit PAS** sans motion CEO (R28)
- ❌ **NE touche PAS** à `core/v9/cycle_memory.py`, `bayesian_predictor.py`, `predictive_engine.py`, `meta_strategy_optimizer.py`, `learn_loop.py` (Phase E draft, à stabiliser)
- ❌ **NE lance PAS** `v9_sync_state.py` (écraserait le travail d'OPUS fictif)
- ❌ **NE fais PAS** de motion CEO usurpée (« je commit parce que c'est urgent »)
- ❌ **NE prétends PAS** que Phase E est livré alors qu'elle est untracked

## 5. Critères d'arrêt

- Plus de 2h bloqué sur un livrable → ESCALADE à Søn
- Tests en échec non-fixables en 30 min → documente et passe
- DB live suspectée corrompue par un script → STOP immédiat (mais on est en lecture seule)

## 6. Timing

- T+0 à T+30 min : validation de l'état (git status, DECISIONS_LOG, AGENT.md)
- T+30 min à T+6h : Garde-fous théoriques (3 docs archi + 1 script emergency)
- T+6h à T+12h : Tests d'intégration (3 fichiers test_*.py)
- T+12h à T+18h : Insights DB + bilan global

**Total : 18h de travail utile en attente de motion CEO sur Phase E.**

## 7. Rapport final attendu

À la fin :
1. Liste des fichiers créés (uniquement nouveaux, pas de modif)
2. Tests cumulés : 195 (Phase E draft) + ≥ 65 (Phase F support) = ≥ 260 verts
3. Bilan dans `workspace/perplexity/memory/DECISIONS_LOG.md` §2026-07-18 « Hermès Phase F support (draft, non livré) »
4. 0 commit fait (sauf si motion CEO explicite entre temps)

## 8. Motion de fin

**Phrase à mettre dans ta dernière réponse** :
> « Mission Hermès terminée — X livrables créés, Y tests verts, 0 commit. En attente motion CEO pour (a) commit Phase E (b) audit DB Option (c) redémarrage capture_server. »

---

*Brief rédigé le 2026-07-18 par ZCode, à la demande de Søn. Sans fiction OPUS, sans分身 pédagogique.*
*R28 strict : aucun commit sans motion CEO explicite.*
