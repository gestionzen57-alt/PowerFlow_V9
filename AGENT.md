# AGENT.md — PowerFlow V9

## Statut
Document racine du système PowerFlow V9. Phase 9.9 + 9.10-RULE29 + Sprint Søn Mode A + Q1→Q5 + Autopilot CEO + ORDER-BRIDGE + P2 shadow + P3-CONSUME-EXTEND livrés. 30 règles doctrine (R20' lecture-first, R25' vocabulaire descriptif, R28 Hermes git unique, R29 lecture multi-TF, R30 apprentissage WIN/LOSS progressif — assouplies 2026-07-14).

## État système — généré automatiquement

<!-- AUTO:STATE -->
<!-- Généré automatiquement par scripts/v9_sync_state.py — 2026-07-15 21:29 UTC -->
<!-- Ne pas éditer manuellement. Pour forcer : python scripts/v9_sync_state.py -->

| Métrique | Valeur | Source |
|---|---|---|
| HEAD | `1f158ed fix(v9): audit bug regime GBPUSD â€” 2 bugs reels + vote neutre + MTF Confirmation Engine` | `git log --oneline -1` |
| Tests collectés | 1403 | `pytest --collect-only` |
| Tables DB | 23 | `sqlite3 data/v9_forces.db` |
| Index DB | 57 | `sqlite3` |
| Taille DB | 1.43 GB | `du -h` |
| Décisions | 66159 | `SELECT count(*) FROM decisions` |
| Forces snapshots | 115877 | DB |
| Scènes | 66178 | DB |
| Principle evals | 621632 | DB |
| Régime snapshots | 529280 | DB |
| Paper trades | 58 | DB |
| Principle scores | 5 | DB |
| Principes YAML | 53 (25 ACTIVE + 23 SHADOW) | `ls core/v9/principles/*.yaml` |
| Serveurs MCP | 8 | `ls mcp_servers/*.py` |
| Crons Ready | 0 | `schtasks /query` |
| V9_TRADER_MINI_ENABLED | 1 | `config/v9_kill_switches.env` |
| V9_AUTO_CALIBRATOR_ENABLED | 1 | env |
| V9_SHADOW_MODE_ENABLED | 1 | env |
| V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED | 1 | env |
| V9_EXECUTION_ENABLED | 1 | env |

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

## Architecture MCP (7 serveurs)

7 serveurs MCP dans `mcp_servers/`, register dans `.mcp.json` (projet) :

| Serveur | Fichier | Rôle | Appelé en prod |
|---|---|---|---|
| doctrine | `doctrine_server.py` | Lit DOCTRINE.md, règles assouplies | ❌ Tests seulement |
| filesystem | `filesystem_server.py` | Lecture/écriture fichiers V9 | ❌ Tests seulement |
| meta_agent | `meta_agent_server.py` | Bus agent + propositions | ❌ Tests seulement |
| p3_consume | `p3_consume_server.py` | Stats principes, shadow principles | ❌ Tests seulement |
| pipeline | `pipeline_server.py` | Start/stop pipeline, run scripts whitelist | ❌ Tests seulement |
| sqlite | `sqlite_server.py` | Requêtes SQL sur data/v9_forces.db | ❌ Tests seulement |
| telegram | `telegram_server.py` | Envoi notifications Telegram | ✅ 3 scripts production |

**Note** : 6/7 serveurs ne sont appelés que par les tests. Le register `.mcp.json`
permet aux clients MCP (Claude, ZCode) de les découvrir. Les scripts production
appelent directement les modules `core/v9/*.py` sans passer par MCP.

## État courant — P3-CONSUME-EXTEND en cours (Hermes 2026-07-14)
- **Branche** : `feat/v9-foundation-clean` (up-to-date avec origin)
- **Chaîne cognitive** : 9+1 couches complètes (Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Régime → Principes → Signal → Décision → Arbiter/RiskManager → PaperTrade/Heartbeat)
- **Principes** : 25 ACTIVE + 28 SHADOW = 53 YAML (25 ACTIVE invariants depuis 2026-07-10, +26 `*_ADAPTIVE` P3-CONSUME-EXTEND Hermes 2026-07-14 tous SHADOW R25' strict, +ADAPTIVE_VOL_GATE, +SIGNAL_OPEN)
- **Contexte propagé** : **31+ champs** contractualisés dans `docs/architecture/CONTEXT_CONTRACT.md`
- **NewsContext** : Actif — 5 champs (`news_phase` PRE_NEWS/NEWS_SHOCK/POST_NEWS/NEUTRE, `news_distance_min`, `news_importance`, `news_session_clean`, `news_type`)
- **Phase 9.7 paper-trade** : modules livrés (Arbiter, RiskManager, PaperTradeLogger). 71 paper trades clôturés (66W/5L)
- **`order_executor.py`** : créé 2026-07-13 (Brief Q5), double-verrou (`V9_EXECUTION_ENABLED` + HITL), exécution réelle Phase 12 INTERDITE
- **Doctrine** : 30 règles immuables (R20' lecture-first, R25' descriptif, R28 assoupli 2026-07-14, R7/R22 assouplis 2026-07-14)
- **Mémoire** : interne V9, 0 dépendance mem0 (archivé)
- **Agentic map** : `agents/AGENTIC_MAP.md` (3 options VPS, 17 rôles, 6 points ouverts tranchés)
- **Inspiration** : 2 vidéos YouTube FABLE (loop engineering + distillation LLM) cartographiées dans `workspace/perplexity/inspiration/`
- **Signal live** : `preparer_entree GBPUSD M5` haussière conf=100 (2026-07-06 14:35 UTC)

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
- Tick lecture complémentaire MT5
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
- `docs/ROADMAP.md` (phases 9-13)
- `docs/DOC_GOVERNANCE.md`
- `docs/STATE.md` (détail vivant par phase)
- `docs/CACHE_BOARD.md` (tableau de reprise compact)
- `workspace/perplexity/ACTIVE_TASKS.md`
- `workspace/perplexity/memory/DECISIONS_LOG.md`
- `docs/architecture/CONTEXT_CONTRACT.md` (contrat propagation inter-couches)
- `docs/deployment/V9_AUTOMATION_RUNBOOK.md` (reboot/ouverture marché/reprise session)

## Rituel de démarrage session (ordre obligatoire)
1. `git pull` + `pytest tests/ -q` → confirmer base saine
2. [Marché ouvert ?] OUI → `python scripts/v9_calibration.py --analyze` OBLIGATOIRE
3. Périmètre explicité : un chantier, une livraison complète (R22 assouplie 14/07 : sous-unités livrables autorisées pour chantiers complexes)
4. Implémentation
5. Tests verts (zéro régression non justifiée — règle 7, assoupli 2026-07-14)
6. `CONTEXT_CONTRACT.md` mis à jour si nouveau champ
7. Principes YAML consommateurs mis à jour (règle 23)
8. Commits atomiques (1 par unité logique)
9. `DECISIONS_LOG.md` — 1 entrée par décision structurante
10. `STATE.md` à jour
11. `git push origin feat/v9-foundation-clean`