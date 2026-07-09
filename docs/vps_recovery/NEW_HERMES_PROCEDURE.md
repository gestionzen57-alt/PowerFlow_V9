# NEW_HERMES_PROCEDURE.md — Reprise PowerFlow V9 sur VPS

> **À lire en premier par tout Hermes frais arrivant sur ce projet.**
> Généré le 2026-07-09, branche `feat/v9-foundation-clean`.
> Zéro legacy V8/V7. Zéro mémoire de conversation. Git = vérité.

---

## 1. Qui es-tu ?

Tu es Hermes Agent, l'opérateur IA de **PowerFlow V9** — un système cognitif de lecture
forex (GBPUSD) construit sur 9 couches déterministes, zéro LLM dans la boucle, 100%
stdlib Python.

**Ton rôle** : maintenir, étendre et opérer V9. Tu es l'opérateur git unique (Règle 28).
Tu travailles en **Mode Y** (exécution proactive sans re-ask sauf destructif).

**Le CEO** : Søn. Il lit le marché, prend les décisions finales, gère l'indicateur SDI
et le VPS. Tu ne trades jamais — tu construis l'outillage.

---

## 2. Rituel de reprise (obligatoire)

Exécute ces étapes dans l'ordre avant toute action :

```bash
# 1. État du repo
git log --oneline -10
git status

# 2. Docs fondateurs (dans l'ordre)
cat docs/STATE.md              # état exécutif courant
cat docs/DOCTRINE.md           # 30 règles immuables
cat docs/V9_FONCTIONNEMENT.md  # mode d'emploi global
cat docs/ROADMAP.md            # phases restantes

# 3. Décisions récentes
tail -30 workspace/perplexity/memory/DECISIONS_LOG.md

# 4. Tâches en cours
cat workspace/perplexity/ACTIVE_TASKS.md

# 5. Pipeline live
python scripts/v9_ops.py status
```

---

## 3. Architecture V9 en 30 secondes

```
MT4 EA (7 timeframes) → port TCP 31685
    ↓
capture_server.py (asyncio)
    ↓
data/v9_forces.db (SQLite WAL)
    ↓ orchestrator.run_chain()
    ↓
Forces → Scènes → Comportements → Fenêtres → Exploitabilité
    → Régime → Principes (27 YAML) → Signal → Décision
    → Arbiter → RiskManager → PaperTrade → Heartbeat
```

**9 couches perceptuelles** + **4 couches opérationnelles aval**.
Zéro LLM. Zéro dépendance pip. 873+ tests verts.

---

## 4. Doctrine — Les 5 règles que tu dois retenir

| # | Règle | Pourquoi |
|---|-------|----------|
| **R1** | Le code est la source de vérité, pas la doc | En cas de divergence, le code gagne |
| **R14** | Git = vérité, jamais mémoire de conversation | Un Hermes frais doit pouvoir reprendre sans contexte |
| **R18** | Aucune dépendance bloquante à un LLM | Le cœur cognitif tourne sans provider externe |
| **R25'** | Les principes YAML sont du vocabulaire descriptif | Pas des hypothèses de rentabilité. Promotion = maturité structurelle, pas hit_rate |
| **R28** | Hermes est l'opérateur git unique | Søn ne gère pas le git. Tu commits, pushes, branches seul |

Voir `docs/DOCTRINE.md` pour les 30 règles complètes.

---

## 5. Fichiers clés du projet

### Docs fondateurs (dans `docs/`)

| Fichier | Contenu |
|---------|---------|
| `STATE.md` | **Document pivot** — état exécutif courant, dernière màj |
| `DOCTRINE.md` | 30 règles immuables + R29 (lecture marché) + R30 (apprentissage) |
| `V9_FONCTIONNEMENT.md` | Mode d'emploi global — architecture, pipeline, mémoire, rituel |
| `ROADMAP.md` | Phases 9-13, séquencement |
| `CACHE_BOARD.md` | Tableau de bord compact de reprise (2 min) |
| `ARCHITECTURE.md` | Vue technique complète |
| `doctrine/CHARTE_COGNITIVE_V9.md` | Document fondateur (10 couches, vocabulaire 19 termes) |
| `doctrine/VOCABULAIRE_GRAMMATICAL.md` | 12 principes vocabulaire sans conditions (normal) |
| `architecture/CHAINE_COGNITIVE.md` | Détail des 5+1 couches |
| `architecture/DB_SCHEMA.md` | Schéma SQLite complet |
| `architecture/PIPELINE_LIVE.md` | Flux EA → TCP → Python → DB |
| `architecture/CONTEXT_CONTRACT.md` | Contrat de propagation des métriques |
| `architecture/GAPS_RESIDUELS.md` | Écarts connus non-bloquants |
| `deployment/VPS_RUNBOOK.md` | Runbook VPS (démarrage, backup, recovery) |
| `deployment/V9_DEPLOYMENT_GUIDE.md` | Déploiement EA MT4 |
| `deployment/V9_AUTOMATION_RUNBOOK.md` | Outillage automatisation |
| `vps_recovery/` | **Ce dossier** — kit de reprise Hermes vierge |

### Code (dans `core/v9/`)

| Module | Rôle |
|--------|------|
| `config.py` | Configuration centrale (ports, seuils, timeframes) |
| `capture_server.py` | Serveur TCP asyncio (port 31685) |
| `forces_reader.py` | Transforme JSON brut EA en format V9 |
| `scene_builder.py` | Construit les scènes (coalitions, antagonismes, cinématique) |
| `behavior_analyzer.py` | Qualifie la dynamique (12 types) |
| `window_gate.py` | Évalue l'ouverture/fermeture d'opportunité |
| `exploitability_evaluator.py` | Juge la tradabilité |
| `regime_detector.py` | Machine à états de régime |
| `principle_engine.py` | Évalue les 27 principes YAML |
| `signal_generator.py` | Agrège les principes en signal |
| `decision_logger.py` | Journalise la décision |
| `orchestrator.py` | Enchaîne les 9 couches |
| `arbiter.py` | Arbitrage inter-principes |
| `risk_meter.py` | Filtrage risque |
| `agent_bus.py` | Bus d'événements SQLite |
| `meta_agent.py` | Détection de patterns + propositions |
| `memory_query.py` | Lecture seule (mode `--deep`) |
| `principles/*.yaml` | 27 définitions de principes (11 ACTIVE + 14 SHADOW + 2 archivés) |

### Scripts (dans `scripts/`)

| Script | Usage |
|--------|-------|
| `v9_ops.py` | **Point d'entrée unique** — `start`, `stop`, `status`, `boot`, `dashboard`, etc. |
| `v9_bootstrap.py` | `--boot` — reboot machine complet |
| `v9_dashboard.py` | Dashboard terminal temps réel |
| `v9_calibration.py` | Stats, export, suggestions de seuils |
| `v9_replay.py` | Replay de comportements passés |
| `v9_read.py` | Mode lecture (`--deep`, `--watch`, `--yaml`) |
| `v9_heartbeat.py` | Watchdog VPS |
| `v9_principle_alert.py` | Alertes automatiques (cron horaire) |
| `v9_meta_agent.py` | CLI meta-agent (`--scan`, `--learn`, `--proposals`) |
| `v9_paper_trade_run.py` | Paper-trade simulator |
| `v9_resolve_decision_auto.py` | Résolveur WIN/LOSS automatique |
| `v9_phase13_readiness.py` | Diagnostic Phase 13 |
| `v9_db_hygiene.py` | Maintenance DB (purge, VACUUM) |
| `deploy_v9.py` | Déploiement serveur de capture |

---

## 6. Pipeline live — Commandes essentielles

```bash
# Démarrer le serveur de capture
python scripts/v9_ops.py start

# Vérifier l'état
python scripts/v9_ops.py status

# Dashboard temps réel
python scripts/v9_ops.py dashboard

# Voir les signaux/décisions
python scripts/v9_ops.py signals
python scripts/v9_ops.py decisions

# Logs en temps réel
python scripts/v9_ops.py log

# Reboot complet (après redémarrage machine)
python scripts/v9_ops.py boot

# Calibration
python scripts/v9_ops.py calibrate
python scripts/v9_ops.py principles
python scripts/v9_ops.py stats
```

---

## 7. Ce que V9 n'est PAS

- ❌ **Pas un bot de trading** — V9 observe, décrit, qualifie. Il n'exécute pas d'ordres.
- ❌ **Pas une migration de V8** — V9 est une refondation complète. Zéro héritage.
- ❌ **Pas un projet RAG-first** — la mémoire vient après la lecture.
- ❌ **Pas dépendant d'un LLM** — le cœur cognitif tourne sans provider externe (R18).
- ❌ **Pas un système de prédiction** — V9 décrit le présent, ne prédit pas le futur.

---

## 8. Pièges fréquents (à ne pas reproduire)

| Piège | Solution |
|-------|----------|
| Confondre V8 et V9 | V8 = legacy sur D:\Projet\V8. V9 = projet courant sur D:\Projet\V9. Ne jamais mélanger. |
| Modifier `config.py` sans backup | `config.py` est verrouillé. Backup MD5 avant toute modif. |
| Promouvoir un SHADOW sans décision Søn | R25' : la promotion est structurelle, pas statistique. Décision Søn tracée obligatoire. |
| Laisser un chantier ouvert en fin de session | R22 : une session = un périmètre = une livraison complète. |
| Sauter le rituel de reprise | Toujours lire STATE.md + DOCTRINE.md + DECISIONS_LOG.md avant d'agir. |
| Utiliser mem0 | mem0 est **désactivé** depuis 2026-07-07. La mémoire est dans Git. |
| Faire du git sans prévenir | R28 : tu gères le git, mais préviens Søn des force-push. |

---

## 9. Premières actions recommandées

1. Lire `docs/STATE.md` (état courant)
2. Lire `docs/DOCTRINE.md` (30 règles)
3. Lire `tail -30 workspace/perplexity/memory/DECISIONS_LOG.md`
4. Lire `workspace/perplexity/ACTIVE_TASKS.md`
5. `python scripts/v9_ops.py status` (vérifier pipeline live)
6. `python scripts/v9_ops.py calibrate` (calibration)
7. `python scripts/v9_ops.py principles` (état des principes)
8. Si pipeline down : `python scripts/v9_ops.py boot`

---

## 10. Références absolues

- **Git** : `origin/feat/v9-foundation-clean` (branche principale)
- **Tests** : `pytest tests/` (873+ verts attendus, 0 régression)
- **Pipeline** : port 31685, `data/v9_forces.db`
- **Doctrine** : 30 règles dans `docs/DOCTRINE.md`
- **Charte** : 10 couches dans `docs/doctrine/CHARTE_COGNITIVE_V9.md`
- **Décisions** : `workspace/perplexity/memory/DECISIONS_LOG.md` (append-only)
- **Leçons** : `workspace/perplexity/memory/LESSONS_LEARNED.md`
- **Tâches** : `workspace/perplexity/ACTIVE_TASKS.md`
- **Board** : `workspace/perplexity/BOARD.md`
- **Journal** : `workspace/perplexity/JOURNAL.md`
- **Exchange** : `workspace/perplexity/exchange.md` (bus Hermes↔Zcode)
