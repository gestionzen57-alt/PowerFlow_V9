# V9 — Fonctionnement global (mode d'emploi)

> **Statut** : Document de référence unique. Mis à jour à chaque phase.
> **Audience** : Søn (CEO), Zcode (deepseek-v4-flash), Claude Code, futurs agents.
> **Source de vérité** : ce doc + `docs/STATE.md` (état) + `docs/DOCTRINE.md` (règles) + `docs/ROADMAP.md` (séquencement) + Git.
> **Remplace** : aucune lecture d'un autre fichier ne doit contredire celui-ci.

---

## 1. Qu'est-ce que V9 ?

**PowerFlow V9** est un système cognitif de trading forex (GBPUSD prioritaire)
qui observe le marché en continu, le qualifie à travers 9 couches d'analyse
séquentielles, et journalise ses décisions pour validation humaine avant
toute exécution (paper-trade d'abord, jamais d'ordre réel avant Phase 12).

V9 est **mono-writer** (le pipeline live écrit, le dashboard lit) et **mono-LLM-non-bloquant** (aucun appel LLM ne peut bloquer la chaîne cognitive — règle 18).

**Trois piliers** :
1. **Perception** : 9 couches de lecture du marché (Forces → Décision).
2. **Mémoire** : interne (Git-versionnée), 3 types (persistante / temporaire / swap).
3. **HITL** : l'humain (Søn) garde le dernier mot sur toute action destructrice (paper-trade, futures ordres réels).

---

## 2. Architecture en 9 couches

| # | Couche | Module | Source | Consommateur aval |
|---|---|---|---|---|
| 1 | Forces | `core/v9/forces_reader.py` | MT4 (port 31685 TCP) | Scènes |
| 2 | Scènes | `core/v9/scene_builder.py` | forces_snapshots | Comportements |
| 3 | Comportements | `core/v9/behavior_analyzer.py` | scenes | Fenêtres |
| 4 | Fenêtres | `core/v9/window_gate.py` | behaviors | Exploitabilité |
| 5 | Exploitabilité | `core/v9/exploitability_evaluator.py` | windows | Principes |
| 6 | Régime | `core/v9/regime_detector.py` | forces_snapshots (multi-TF) | Principes |
| 7 | Principes (27 YAML) | `core/v9/principle_engine.py` | scenes + behaviors + windows + exploitability + regime | Signal |
| 8 | Signal | `core/v9/signal_generator.py` | principles ACTIVE | Décision |
| 9 | Décision | `core/v9/decision_logger.py` | signals | Phase 9.7 (paper) |

**Couche transversale** : `core/v9/news_context.py` (calendrier économique,
5 champs, 7 tests) — injecte `news_phase`, `news_distance_min`, etc. dans
`_load_shared_context()` **en dernier** (cf. bug ANTAGONIST_NODE 2026-07-06).

**Source unique de schéma DB** : `core/v9/db_schema.py` expose
`init_all_dbs()` (11 tables dans l'ordre amont→aval) + `get_connection()`
(WAL + busy_timeout 30s) + `migrate_source_type()` (8 tables, règle 12).

**Contrat de propagation** : `docs/architecture/CONTEXT_CONTRACT.md` —
toute métrique nouvelle doit y être tracée (PROPAGÉ ou DORMANT justifié).
Test gardien : `tests/test_context_propagation.py` (4/4 verts).

---

## 3. Pipeline live

### 3.1 Démarrage (PC local ou VPS)

```bash
cd /d/Projet/V9
python scripts/v9_bootstrap.py --boot     # prépare, vérifie, lance
# ou plus manuel :
python scripts/v9_ops.py start            # serveur de capture (port 31685)
python scripts/v9_telegram_notifier.py --watch    # notifier Telegram (boucle)
```

Crons Windows installés (Phase 9.8) :
- `V9_TelegramNotifier` — au login (boucle watchdog interne)
- `V9_DailyReport` — tous les jours à 23:00 UTC
- `V9_HeartbeatCheck` — toutes les 5 min (`scripts/v9_heartbeat.py --check`)
- `V9_HeartbeatAlert` — toutes les 60 min (`scripts/v9_heartbeat.py --heartbeat`)

### 3.2 Flux de données temps réel

```
MT4 EA (forces) → port 31685 → capture_server.py
                                     ↓ INSERT
                                forces_snapshots (couche 1)
                                     ↓ scene_builder
                                scenes (couche 2)
                                     ↓ behavior_analyzer
                                behaviors (couche 3)
                                     ↓ window_gate
                                windows (couche 4)
                                     ↓ exploitability
                                exploitability (couche 5)
                                     ↓ regime_detector (en parallèle)
                                regime_snapshots (couche 6)
                                     ↓ principle_engine (fusion)
                                principle_evaluations (couche 7)
                                     ↓ signal_generator
                                signals (couche 8)
                                     ↓ decision_logger
                                decisions (couche 9) → Telegram notifier
                                                      ↓
                                                Phase 9.7
                                                      ↓
                                                paper_trades
```

### 3.3 Snapshot live (lecture seule)

```bash
python scripts/v9_dashboard.py --once          # état pipeline
python scripts/v9_daily_report.py --no-color  # rapport quotidien
python scripts/v9_heartbeat.py --check         # watchdog 1 cycle
```

---

## 4. Mémoire V9 (zéro dépendance externe)

5 fichiers internes (Git-versionnés) :

| Fichier | Rôle | Cycle de vie |
|---|---|---|
| `workspace/perplexity/memory/memory.md` | Conventions immuables + état quotidien | Versionné |
| `workspace/perplexity/memory/MEMORY_CANON.md` | Index doctrinal | Versionné |
| `workspace/perplexity/memory/DECISIONS_LOG.md` | Décisions datées (4 champs) | Append-only |
| `workspace/perplexity/memory/LESSONS_LEARNED.md` | Retours sessions → doctrine | Append-only |
| `workspace/perplexity/memory/mem0_archive/` | Sauvegarde mem0 cloud (vide) | Conservé pour rollback |

Bus live :
- `workspace/perplexity/exchange.md` — coordination Hermes↔Zcode
- `workspace/perplexity/JOURNAL.md` — deltas opérationnels
- `workspace/perplexity/LIVE_LOG_YYYYMMDD.md` — snapshots horodatés
- `workspace/perplexity/INCIDENTS.md` — incidents datés
- `workspace/perplexity/mini_checkpoints/` — checkpoints courts intra-session
- `workspace/perplexity/inspiration/` — notes d'inspiration externes (YouTube, articles)

**Rituel de reprise de session** (remplace mem0_profile) :
1. `cat workspace/perplexity/BOARD.md`
2. `cat docs/CACHE_BOARD.md` (si existe) ou `docs/STATE.md`
3. `cat workspace/perplexity/ACTIVE_TASKS.md`
4. `tail -20 workspace/perplexity/memory/DECISIONS_LOG.md`
5. `cat workspace/perplexity/exchange.md`
6. `git log --oneline -10 && git status`

**Rituel d'écriture** (remplace mem0_conclude) :
- Fait doctrinal → append dans `DECISIONS_LOG.md` (4 champs)
- Leçon session → append dans `LESSONS_LEARNED.md`
- Delta opérationnel → append dans `JOURNAL.md` (max 5 lignes)
- Note d'inspiration → `workspace/perplexity/inspiration/INSPIRATION_<date>_<sujet>.md`

**mem0 est désactivé** depuis 2026-07-07 (cf. `mem0_archive/README.md`).
Restauration possible uniquement sur décision explicite Søn (règle 14).

---

## 5. Hiérarchie de vérité (règle 14)

```
1. Git (commit history)                    ← vérité absolue
2. docs/STATE.md + checkpoints/            ← doc vivante
3. workspace/perplexity/exchange.md        ← bus Hermes↔Zcode
4. workspace/perplexity/JOURNAL.md         ← deltas ops
5. workspace/perplexity/memory/*.md        ← durable, versionné
6. Mémoire de conversation                 ← JAMAIS authoritative
7. mem0 (cloud)                            ← DÉSACTIVÉ
```

**Divergence détectée** à n'importe quel niveau → signaler à Søn AVANT d'agir.

---

## 6. Doctrine — 27 règles immuables

Voir `docs/DOCTRINE.md` (résumé opérationnel) + `docs/doctrine/*.md` (détail).

Règles clés pour le fonctionnement courant :
- **Règle 1** : Le code est la source de vérité, pas la doc.
- **Règle 6** : L'orchestrateur ne crash jamais (try/except par couche).
- **Règle 7** : Tests obligatoires avant commit — 0 régression tolérée.
- **Règle 12** : `source_type` ∈ {live, replay} sur 8 tables dérivées.
- **Règle 14** : Git = vérité, jamais mémoire de conversation.
- **Règle 18** : Aucune dépendance bloquante à un LLM pour le cœur cognitif.
- **Règle 22** : Une session = un périmètre = une livraison complète.
- **Règle 25** : SHADOW → ACTIVE = hit_rate ≥ 60% sur ≥ 50 déclenchements live.
- **Règle 26** : 1 commit / DECISIONS_LOG / STATE.md par session.
- **Règle 27** : DORMANT > 2 phases = réévaluation (PROMU ou SUPPRIMÉ).

---

## 7. Phases (état actuel)

| Phase | Statut | Livré |
|---|---|---|
| 1-8 | ✅ Terminées | 2026-06-30 |
| 9 (Décision + Principes) | ✅ Canonisée | 2026-07-05 |
| 9.7 (Paper-Trade Simulator) | ✅ Livrée | 2026-07-07 (commit `d505bec`) |
| **9.8 (VPS-READY)** | ✅ Livrée | 2026-07-07 (commit `4aa4fd3`) |
| 10 (Fédération d'agents) | ⏸️ Gelée | doctrine |
| 11 (Layer MT5 ticks) | ⏸️ Planifiée | conditionnelle VPS stable 24-48h |
| 12 (Exécution d'ordres) | ⏸️ Planifiée | interdite fondateur |
| 13 (Apprentissage + auto-cal) | ⏸️ Planifiée | conditionnelle WIN/LOSS ≥ 50 |

**Condition pour Phase 11** : VPS déployé + ≥ 1 paper-trade résolu (WIN ou LOSS) + ≥ 1 session London/NY avec window exploitable M15/H1.

---

## 8. Tests

- **Total** : 547 verts (0 régression, règle 7).
- **Gardien DB** : `tests/test_context_propagation.py` (4/4) — CONTEXT_CONTRACT conforme.
- **Pipeline bout-en-bout** : `tests/test_pipeline_end_to_end.py` (1/1) — orchestrateur complet.
- **News** : `tests/test_news_context.py` (7/7) — calendrier économique.
- **Watchdog** : `tests/test_v9_heartbeat.py` (20/20) — port 31685 + DB freshness + Telegram.

Lancer : `python -m pytest tests/ -q` (~50s).

---

## 9. Scripts ops principaux

| Script | Usage |
|---|---|
| `v9_bootstrap.py` | Boot complet (prépare, vérifie, lance) |
| `v9_ops.py` | Start/stop serveur de capture + dashboard CLI |
| `v9_dashboard.py` | Snapshot live lecture seule |
| `v9_daily_report.py` | Rapport quotidien (23h UTC) |
| `v9_heartbeat.py` | Watchdog port + DB + Telegram |
| `v9_telegram_notifier.py` | Notifier décisions + chat Hermes |
| `v9_paper_trade_run.py` | Orchestrateur paper-trade (Phase 9.7) |
| `v9_resolve_decision.py` | Saisie WIN/LOSS manuelle |
| `v9_scoring.py` | Hit rate par principe (Phase 9.7) |
| `v9_calibration.py` | Analyse calibration (règle 20) |
| `v9_replay.py` | Replay historique (Phase 8) |
| `v9_market_open.py` | Mini-checkpoint ouverture marché |
| `v9_session_resume.py` | Reprise de session |

---

## 10. Anti-patterns à éviter (V8 lessons)

- **Ouvrir Phase 10 (fédération) avant stabilisation live** (cf. V8 dette).
- **Expansion sans consolidation** : 0 chantier expansion tant que C-1→C-4 non livrés.
- **Inventer des seuils numériques absents de DOCTRINE.md** (cas : "WIN/LOSS ≥ 20" inventé 2026-07-07, corrigé).
- **Toucher `core/v9/config.py`, YAML principes, `orchestrator.py`** sans décision Søn.
- **Mémoire de conversation comme source de vérité** (toujours Git d'abord).
- **Commit direct sans tests verts** (règle 7).
- **Session sans DECISIONS_LOG / STATE.md à jour** (règle 26).

---

## 11. Handoff Søn

À toi de jouer, post-déploiement VPS :
1. Installer crons (déjà fait pour heartbeat, vérifier Telegram/Daily).
2. Recevoir Telegram "✅ V9 alive" toutes les 60 min.
3. Observer pipeline live 24-48h.
4. Si stable → ouvrir Phase 11 (Layer MT5 ticks) — décision dans DECISIONS_LOG.
5. Résoudre WIN/LOSS manuellement via `v9_resolve_decision.py` pour alimenter scoring.

**Rappel** : VPS 1 GB / 1 vCPU / 5 GB SSD / port 31685 ouvert. DNS
`vps.powerflow.local` à pointer vers VPS. Procédure rollback §5 du
checkpoint `CHECKPOINT_20260707_VPS_READY.md`.

---

## 12. LLM usage policy (règle 18 + inspiration FABLE 2)

**Principe fondamental** : le cœur cognitif V9 = code Python pur, AUCUN LLM dans la boucle 1→9. Le LLM est un **observateur** (Telegram, scoring, calibration), jamais un **décideur** (chaîne de trading).

### Ce que le LLM peut faire
- Répondre aux messages Telegram texte (chat Hermes, forwarded texte libre).
- Générer des rapports lisibles (`v9_daily_report.py` est Python pur, mais un LLM peut réécrire le rapport en français naturel si demandé).
- Calculer des hit rates (`v9_scoring.py` est Python pur sur DB, mais un LLM peut commenter les résultats).
- Reformuler une décision complexe pour l'opérateur.

### Ce que le LLM ne peut PAS faire
- **Décider d'ouvrir un trade** (paper ou réel) — c'est `core/v9/arbiter.py` (Python pur).
- **Modifier un principe YAML** — c'est `core/v9/principles/*.yaml` (gelés par doctrine).
- **Altérer le contexte cognitif** injecté dans `_load_shared_context()`.
- **Court-circuiter le pipeline** (forcer un signal, ignorer une fenêtre NON exploitable, etc.).
- **Tourner sur VPS** en production H24 (1 GB RAM = pas de marge pour un LLM).

### Providers LLM configurés (D:/hermes/profiles/powerflow/config.yaml)
- `ollama-local` — modèles locaux (qwen25-fast, phi3-fast, gemma3-fast, llama-fast) — défaut
- `openrouter` (fallback principal) — modèles distants via API
- `nous` — fallback
- `nvidia` — fallback

### Modèles utilisés
- **Chat non-reasoning** : `qwen3-coder-next:cloud` (rapide, peu coûteux)
- **Chat reasoning** : `deepseek-v4-flash` (réponse dans le bloc `reasoning`, pas `content`)
- **Mini-modèle local Phase 13** : distillation du comportement V9 (4-12B quantifié) — voir `INSPIRATION_20260707_FABLE2.md` §3.1

### Quantization policy (Phase 13+)
- Q4_K_M = minimum acceptable (erreurs < 5%)
- Q5_K_M / Q6_K = défaut recommandé
- Q8_0 = max précision, RAM × 2
- F16 = recherche uniquement (pas production)
- Source : inspiration FABLE 2, distillation Claude Fable via LM Studio (juillet 2026)

### Référence
- `docs/DOCTRINE.md` règle 18 (pas de LLM bloquant dans le cœur cognitif)
- `INSPIRATION_20260707_FABLE.md` (loop engineering)
- `INSPIRATION_20260707_FABLE2.md` (distillation LLM + LM Studio)
- `agents/AGENTIC_MAP.md` §3 (3 options architecture)

---

**Ce document est vivant.** Toute évolution doit être tracée dans
`memory/DECISIONS_LOG.md` et re-validée par Søn.
Référence : `docs/STATE.md`, `docs/DOCTRINE.md`, `docs/ROADMAP.md`,
`workspace/perplexity/BOARD.md`.