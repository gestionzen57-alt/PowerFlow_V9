# AGENTS.md — PowerFlow V9 (mémoire workspace ZCode)

> **Source de vérité** : `AGENT.md` (document racine). Ce fichier est un pointeur
> pour ZCode — il référence la mémoire du projet et les conventions de travail.

## Mission

PowerFlow V9 est un système de lecture comportementale des forces de marché.
Il observe, structure, mémorise, confronte et qualifie les dynamiques de marché
avant toute logique d'exploitabilité ou d'exécution.

Ne jamais demander au système de trader ce qu'il ne sait pas encore décrire.

## Documents pivots (à lire au démarrage session)

| Document | Rôle | Quand |
|---|---|---|
| `AGENT.md` | État système auto-généré + mission + routing | Démarage |
| `SOUL.md` | **Âme du système** — philosophie, architecture 4 couches, boucle fermée, état | **Démarage (OBLIGATOIRE)** |
| `docs/STATE.md` | État vivant par phase | Démarage |
| `docs/DOCTRINE.md` | 30 règles (R25'' auto-promotion, R30 boucle fermée) | Avant commit |
| `docs/CACHE_BOARD.md` | Tableau de reprise compact | Reprise session |
| `workspace/perplexity/memory/DECISIONS_LOG.md` | Décisions structurantes | Avant commit |
| `workspace/perplexity/memory/MEMORY_CANON.md` | Éléments stables | Référence |
| `docs/architecture/CONTEXT_CONTRACT.md` | Contrat propagation inter-couches | Si nouveau champ |
| `docs/ROADMAP.md` | Phases 9-13 | Planification |
| `memory/memory.md` | Mémoire persistante validée | Référence |

## SOUL.md — Résumé exécutif (chargé automatiquement)

> **Philosophie** : Stratège autonome. Lecture haute définition. Aucun angle mort.
> Le système voit, propose, exécute. Il n'attend pas.

### Architecture 4 couches
```
LECTURE (perception) → DÉCISION (principes) → OPTIMISATION (boucle fermée) → EXÉCUTION (simulation)
```

### Piliers
1. **Détection proactive** — scan continu, alerte automatique
2. **Optimisation continue** — auto-calibrateur + auto-optimizer
3. **Exécution sans friction** — SHADOW→ACTIVE auto, TP/SL auto-ajustés
4. **Lecture haute définition** — MTF, session, volatilité, vélocité modulent la décision

### Boucle fermée
Pipeline → Principes → Signal → Décision → Paper trade → Résolution → Calibration → Optimisation → Pipeline

### État (2026-07-16)
- **1497 tests**, 44 ACTIVE + 9 SHADOW, 0% hit rate → 0
- **11 crons**, Telegram, Dashboard web
- **9 gaps audités et résolus** (MTF, session, volatilité, vélocité, etc.)
- **Bug latent corrigé** : auto-promotion R30 était silencieusement plantée

### Prochaine étape
J+2 : vérifier les 4 SHADOW en observation → promouvoir si WR sain → PRICE_LAG sous 60%

## Règles critiques (rappel — détail dans DOCTRINE.md)

- **R7** : tests verts avant commit, régressions justifiées dans DECISIONS_LOG
- **R8** : doc mise à jour à chaque livraison
- **R14** : Git = source de vérité
- **R18** : pas de LLM dans le cœur cognitif (code pur)
- **R22** : 1 session = 1 périmètre = 1 livraison (assoupli 14/07)
- **R25'** : promotion SHADOW→ACTIVE conditionnée (assoupli 14/07)
- **R26** : 1 commit + 1 DECISIONS_LOG + STATE.md par session
- **R28** : Hermes opérateur git unique (assoupli 14/07, délégation possible)

## Rituel de démarrage session

1. `git pull` + `pytest tests/ -q` → base saine
2. Marché ouvert ? → `python scripts/v9_calibration.py --analyze` OBLIGATOIRE
3. Périmètre explicité
4. Implémentation
5. Tests verts
6. CONTEXT_CONTRACT.md si nouveau champ
7. Principes YAML consommateurs (R23)
8. Commits atomiques
9. DECISIONS_LOG entry
10. STATE.md à jour
11. `git push` (Hermes ou mandat CEO)

## Bus agent V9 (pont inter-IA)

Le bus `data/v9_agent_bus.db` connecte ZCode, Hermes et Claude CLI :

```bash
# Voir les événements en attente
python scripts/agent_bus_cli.py pending

# Consommer ses événements
python scripts/agent_bus_cli.py poll <profile> --source zcode

# Publier une décision
python scripts/agent_bus_cli.py publish <profile> <event_type> '<json>'

# Stats
python scripts/agent_bus_cli.py stats --hours 24
```

## Subagents disponibles (6 profils)

- `rule-guard` — conformité doctrine
- `capture-ops` — opérations pipeline
- `calib-analyst` — calibration seuils
- `data-explorer` — exploration DB
- `learn-analyst` — apprentissage meta-agent
- `session-writer` — clôture session

## Commandes rapides

```bash
python scripts/v9_calibration.py --analyze      # Lecture marché
python scripts/v9_dashboard.py --watch decisions --once
python -m pytest tests/ -q                        # Tests
python scripts/v9_sync_state.py                   # Régénère AGENT.md
```

## Périmètre GELÉ

- Phase 10 : Fédération d'agents
- Skills auto-générés avant canonisation
- Exécution d'ordres réelle avant Phase 12

## Multi-IA (R28)

| Acteur | Rôle | Git direct ? |
|---|---|---|
| Søn | CEO, HITL | Non |
| Hermes | Orchestrateur, opérateur git | OUI (seul) |
| ZCode | Implémentation assistée | Non (via Hermes) |
| Claude CLI | Implémentation assistée | Non (via Hermes) |