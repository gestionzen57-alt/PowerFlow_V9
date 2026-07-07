# AGENTIC_MAP — cartographie de l'architecture agentique V9 (VPS-ready)

> **Statut : chantier de cartographie — AUCUNE logique implémentée.**
> Conformément à `docs/ROADMAP.md` §Phase 10 (fédération d'agents, gelée) et
> `AGENT_BACKLOG.md` (squelettes README-only, pas de logique active), ce document
> décrit la **forme cible** de l'architecture agentique V9 pour préparer un
> déploiement VPS H24 dans les 24h. Il ne démarre aucun chantier de code.

---

## 1. Contexte opérationnel

- **Cible** : déployer V9 sur VPS (1 GB RAM, 1 vCPU, 5 GB SSD, port 31685 ouvert) avec MT4,
  pour tourner en continu H24 sans PC de Søn allumé.
- **Contrainte mémoire** : 1 GB RAM total → daemon Python unique + pool d'agents légers,
  pas de microservices conteneurisés.
- **Contrainte LLM** : VPS = pas d'accès GPU → tous les agents cognitifs doivent être
  *non-bloquants* sur le LLM (cœur cognitif = code pur, LLM = observateur uniquement,
  cf. règle 18 doctrine).
- **Source de vérité** : Git (branche `feat/v9-foundation-clean`), docs/DOCTRINE.md,
  workspace/perplexity/memory/*.md — versionnés et accessibles au VPS via clone.

## 2. Inventaire des squelettes déjà présents

| Dossier | Statut | Rôle pressenti |
|---|---|---|
| `agents/orchestrator/` | README-only | Orchestrateur cognitif (chaîne 9 couches) |
| `agents/force-reader/` | README-only | Lecture des forces MT4 (couche 2) |
| `agents/scene-builder/` | README-only | Construction de scènes (couche 3) |
| `agents/behavior-analyst/` | README-only | Analyse comportements (couche 4) |
| `agents/window-gate/` | README-only | Détection fenêtres (couche 5) |
| `agents/reviewer/` | README-only | Revue / HITL (couche 9) |

→ 6 dossiers, 0 ligne de logique. Cohérent avec `AGENT_BACKLOG.md` (squelette seulement).

## 3. Architecture cible — 3 options à arbitrer

### Option A — Orchestrateur central + workers Python
- 1 daemon `v9_supervisor.py` (déjà livré) = orchestrateur principal.
- Chaque "agent" = fonction Python pure dans `core/v9/`, appelée séquentiellement par le superviseur.
- **Avantage** : 0 surcharge mémoire, debug trivial, conforme règle 18 (LLM non bloquant).
- **Inconvénient** : pas de "vrai" multi-agent (1 process, N fonctions).
- **Complexité VPS** : faible. RAM estimée < 200 MB.

### Option B — Multi-agents asynchrones (asyncio)
- 1 daemon superviseur + N coroutines agents (scene, behavior, window, exploitability, regime, principle, signal, decision, reviewer).
- Communication via bus événements interne (file SQLite ou Redis-lite).
- **Avantage** : vrai parallélisme I/O (lecture forces + scoring simultanés).
- **Inconvénient** : debug complexe, risque de courses, plus de RAM.
- **Complexité VPS** : moyenne. RAM estimée 350-500 MB.

### Option C — Fédération distribuée (agents séparés, RPC)
- Chaque agent = process indépendant sur port différent (31690, 31691...).
- Communication via HTTP/JSON sur localhost.
- **Avantage** : isolation crash, scaling horizontal possible.
- **Inconvénient** : overhead mémoire + latence RPC, surdimensionné pour 1 vCPU.
- **Complexité VPS** : haute. RAM estimée 700+ MB → **non viable sur VPS 1 GB**.

→ **Recommandation par défaut** : Option A pour le VPS 1 GB. Option B seulement si
le monitoring live montre un goulot I/O.

## 4. Cartographie des rôles — qui fait quoi

| Rôle | Composant V9 | Couche cognitive | Bloquant ? |
|---|---|---|---|
| Orchestrateur | `core/v9/orchestrator.py` + `agents/orchestrator/` | Chaîne complète | Oui (chaîne) |
| Lecteur de forces | `core/v9/force_reader.py` (V7→V9) + `agents/force-reader/` | 2 (Forces) | Oui (entrée) |
| Lecteur de scènes | `core/v9/scene_builder.py` + `agents/scene-builder/` | 3 (Scènes) | Oui |
| Lecteur comportements | `core/v9/behavior_analyzer.py` + `agents/behavior-analyst/` | 4 (Comportements) | Oui |
| Détecteur fenêtres | `core/v9/window_gate.py` + `agents/window-gate/` | 5 (Fenêtres) | Oui |
| Évaluateur exploitabilité | `core/v9/exploitability_evaluator.py` | 6 | Oui |
| Détecteur régime | `core/v9/regime_detector.py` | 7 (Régime) | Oui |
| Moteur principes | `core/v9/principle_engine.py` | 7 (Principes) | Oui |
| Générateur signal | `core/v9/signal_generator.py` | 8 | Oui |
| Logger décision | `core/v9/decision_logger.py` | 9 | Oui |
| Arbitre paper-trade | `core/v9/arbiter.py` | 9.7 | Oui (si paper) |
| Risk manager | `core/v9/risk_manager.py` | 9.7 | Oui (si paper) |
| Paper trade logger | `core/v9/paper_trade_logger.py` | 9.7 | Oui (si paper) |
| Superviseur H24 | `scripts/v9_supervisor.py` | Méta | Oui (daemon) |
| Notifier Telegram | `scripts/v9_telegram_notifier.py` | Méta | Non (best-effort) |
| Reporter daily | `scripts/v9_daily_report.py` | Méta | Non (1×/jour) |
| Reviewer HITL | `agents/reviewer/` (à définir) | 9 | Non (humain) |

→ 17 rôles identifiés, 13 déjà implémentés en code V9, 4 en README-only.

## 5. Points de décision ouverts (à trancher avant déploiement VPS)

- [ ] **Option A vs B** : orchestrateur central Python vs asyncio multi-agents ?
- [ ] **Reviewer** : HITL via Telegram (déjà actif via notifier) ou interface web dédiée ?
- [ ] **Persistance** : SQLite actuelle (43k snapshots) → migration Postgres ou conservation SQLite sur VPS ?
- [ ] **MT4 sur VPS** : EA déjà compatible (déjà déployé en local, cf. Phase 7) ou réinstallation ?
- [ ] **Monitoring** : dashboard V9 actuel (`scripts/v9_dashboard.py`) suffit-il ou ajout d'un alerting ?
- [ ] **Rollback** : comment revenir au PC local si VPS tombe ? (DNS swap + Git pull)

## 6. Conformité doctrine — checklist pré-déploiement

- [ ] Règle 7 (tests 0 régression) — `pytest tests/` doit être vert avant commit final
- [ ] Règle 14 (Git = vérité) — `git log --oneline -10` archivé dans checkpoint
- [ ] Règle 18 (pas de LLM bloquant) — vérifier que tous les agents marchent en mode dégradé LLM off
- [ ] Règle 22 (chantier = livraison complète) — pas d'ouverture partielle
- [ ] Règle 25 (calibration-first) — `python scripts/v9_calibration.py --analyze` doit être exécuté
- [ ] Règle 26 (1 commit / DECISIONS_LOG / STATE.md par session)

## 7. Phasage proposé (sous réserve arbitrage Søn)

1. **Court terme (avant VPS)** : trancher Options A vs B (§5) → DECISIONS_LOG.md
2. **Court terme** : implémenter Option A (1-2 commits, ~14 tests) — orchestrateur central Python
3. **Avant VPS** : checkpoint de pré-déploiement (Phase 9.8 — "VPS-READY")
4. **VPS** : déploiement H24 + monitoring 24h + décision go/no-go Phase 11
5. **Post-VPS** : si stable, ouvrir Phase 11 (Layer MT5 ticks) — voir ROADMAP.md

---

**Ce document est vivant.** Toute évolution doit être tracée dans
`workspace/perplexity/memory/DECISIONS_LOG.md` et re-validée par Søn.
Référence : `agents/AGENTIC_MAP.md` (ce fichier), `agents/AGENT_BACKLOG.md`,
`docs/ROADMAP.md`, `docs/DOCTRINE.md`.