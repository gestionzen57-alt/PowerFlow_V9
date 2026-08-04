# AGENTS.md — PowerFlow V10 (mémoire workspace ZCode)

> **🚨 TRANSITION V9 → V10 (2026-08-04 05:00 UTC) — Doctrine libérée**
>
> **V9 = Verrouillé** : 30 règles (R0-R30) qui limitaient l'agentivité.
> **V10 = Libre** : 10 règles simples (R1-R10) qui libèrent le potentiel.
> **V10 = V11 pour Hermes** : même vision, deux noms (CEO mandate).
>
> **Mission V10** : système intelligent, auto-apprenant, qui agit sans
> permission préalable, invente, optimise, trade en micro-lot réel, et
> protège le capital (seul vrai garde-fou R10).
>
> **Héritage V9 conservé** : capture_server, DB, pipeline, doctrine
> sécurité (DD max 10%), tests, MCP tools, skills, alerter Telegram.

## Mission

PowerFlow V10 est un **système cognitif financier auto-apprenant**.
Il observe, structure, invente, apprend, agit, explique, optimise.
Il n'attend pas la permission. Il documente, mesure, s'auto-corrige.

**Le CEO reste dans la boucle stratégique** (capital scaling,
kill switch, bilan mensuel) **mais plus dans la boucle opérationnelle**
(commits, patches, paper trades, calibration).

## Documents pivots (à lire au démarrage session)

| Document | Rôle | Quand |
|---|---|---|
| `AGENTS.md` | État système + doctrine V10 + mission | **OBLIGATOIRE** |
| `SOUL.md` | **Âme V10** — philosophie, 7 modules intelligents, boucle auto | **OBLIGATOIRE** |
| `docs/V10/V10_PLAN_REPARALETTRAGE.md` | Plan directeur 11 phases 90 jours | Référence |
| `docs/V10/GLOSSAIRE.md` | Terminologie CEO Søn (quand créé) | Référence |
| `workspace/perplexity/memory/DECISIONS_LOG.md` | Décisions structurantes | Avant commit |
| `AUDIT_INTEGRITY_2026_08.md` | Audit Phase 180 (chiffres faux) | Référence |
| `data/v9_forces.db` | Source de données brutes (lecture seule V10) | Runtime |

## DOCTRINE V10 — 10 RÈGLES OUVERTES

### R1 — AGIR (le système agit par défaut)
Pas de CEO approval pour les micro-décisions. Le système peut :
killer un process bloqué, commit atomique, push sur feat/*, merge
feat/* → main si tests verts.

### R2 — TESTER EN LIVE (micro-lot, jamais 0)
Micro-lot 0.01 → 0.1 → 0.5 → 1.0 selon Sharpe live. Jamais de paper-only
permanent. Broker : IBKR REST API (Phase 184).

### R3 — INVENTER (génération continue)
Features, stratégies, seuils. Algorithmes génétiques + Bayesian optim.
Chaque génération testée, scorée, gardée ou jetée.

### R4 — APPRENDRE (online learning)
Mise à jour des poids à chaque trade clôturé. RL avec reward = PnL net,
pénalité = -|DD|. ε-exploration = 10%.

### R5 — RÉFLÉCHIR (chain-of-thought)
Chaque décision = raisonnement explicite 5 étapes :
1. "Je vois : [structure], [contexte], [force]"
2. "Je pense : [analyse]"
3. "Je décide : [action] parce que [justification]"
4. "Je risque : [SL] et je gagne : [TP]"
5. "J'apprends : [ce que j'attends de ce trade]"

### R6 — EXPLIQUER (transparence totale)
Chaque chiffre = 1 query SQL traçable. Chaque décision = 1 log structuré.
Chaque modification = 1 commit atomique. Chaque bug = 1 incident post-mortem.

### R7 — MESURER (KPIs auto-archivés, pas de rédaction manuelle)
Métriques continues auto-archivées. Pas de DECISIONS_LOG manuel
(overhead CEO). Alertes auto si KPI franchit seuil.

### R8 — S'AMÉLIORER (boucle fermée 100% auto)
Trade clôturé → métrique → si KPI < seuil → re-calibration auto
→ re-test historique → si mieux → déployer → si moins bien → revert.

### R9 — ÊTRE AUDITABLE (100% vérifiable)
Toutes les décisions reproductibles bit-pour-bit. Toutes les métriques
recalculables. Tous les commits traçables (R14 git = source de vérité).

### R10 — PROTÉGER LE CAPITAL (seul vrai garde-fou)
- DD max 10% capital → halt automatique (kill switch)
- Position max 2% capital par trade
- Levier max 5x (toutes positions confondues)
- Kill switch manuel CEO (override ultime)
- **Pas d'autres restrictions**

## SOUL.md — Résumé exécutif V10

> **Philosophie** : **Système libre, intelligent, auto-apprenant.**
> Le système agit sans permission. Il invente, teste, apprend.
> Il protège le capital. Il s'auto-corrige. Il explique ses décisions.
> Le CEO est dans la boucle stratégique, pas opérationnelle.

### Architecture 7 modules intelligents
```
MODULE 0 — MARCHÉ (Broker IBKR REST API)
   ↓
MODULE 1 — CAPTURE (V9 conservé, port 31685)
   ↓
MODULE 2 — CONTEXTE (TA lecture CEO, V10 réinjecté)
   ↓
MODULE 3 — ALERTES & EXÉCUTION (Telegram + Broker)
   ↓
MODULE 4 — DÉCISION (Chain-of-thought, 5 étapes)
   ↓
MODULE 5 — OPTIMISATION (Bayesian + Genetic)
   ↓
MODULE 6 — APPRENTISSAGE (Online RL, drift detection)
   ↓
MODULE 7 — RÉFLEXION (Self-explanation, post-mortem auto)
```

### Piliers V10
1. **Agence** — agit sans permission
2. **Innovation** — génère en continu
3. **Apprentissage** — online RL, drift detection
4. **Réflexion** — chain-of-thought, self-explanation

### Boucle fermée V10
```
Données brutes → Force/Structure/Context (TA lecture)
   → Décision (CoT) → Trade (micro-lot live)
   → Mesure (PnL, DD, Sharpe) → Apprentissage (RL)
   → Optimisation (Bayesian) → Innovation (nouvelles features)
   → Mesure → ... (boucle infinie)
```

### État (2026-08-04 05:00+ UTC — V10 unlocked)

> ⚠️ **TRANSITION V9 → V10** : doctrine libérée, 30 règles → 10 règles.

- **V9 héritage conservé** : capture_server (port 31685, PID 5128),
  DB v9_forces.db (6.4 GB, 27 tables, 41k signaux/5min), 134+ tests
- **V9 chiffres faux corrigés** (Phase 180) : 337 paper_trades réels,
  WR 44.51% (pas 90.33%), PnL -865 pips (pas +27239)
- **V10 nouveau** : 7 modules intelligents, doctrine R1-R10, micro-lot
  live autorisé, online learning, self-explanation
- **Phase 180 audit** : 5/5 KILL criteria (stratégie perdante) → V10
  va reconstruire à partir de TA lecture, pas des features V9
- **HEAD** : `78c1fa5` (V10 plan directeur, pushé)
  - **Perte moyenne -2.57 pips/trade** → edge decay confirmé
- **Edge decay** : WR 100% les 15-17/07 → 12-43% du 19/07 au 24/07 (effondrement)
- **Doublons détectés** : même (closed_at, direction, pnl) avec trade_id différents (bug insertion)
- **HEAD** : `00786c6` (Phase 179 daemon auto livré, pushé)
- **Tests verts cumulés** : 13/13 Phase 179 + 42/42 Phase 177 + 134+ session totale
- **12 MCP tools** + **6 skills catalogue Hermes** + **3 skills patchés** (Phase 179)
- **Infrastructure** : ✅ port 31685 stable, ✅ pipeline 41 050 signaux/5min, ✅ capture_server PID 5128
- **Perf x10 cumulé** (540ms → 57ms/snapshot)
- **2 modules hedge fund** : `core/v9/v9_drawdown_protector.py` (5 paliers), `core/v9/v9_risk_parity.py` (5 paires + USDCAD blacklist)
- **Cœur cognitif V10 LIVRÉ 04/08 14:20 UTC** (autopilote) : `core/v10/`
  (v10_force F1-F5, v10_structure S1-S9, v10_context C1-C7, v10_orchestrator
  → V10 Signal A1/A2/A3/NONE + CoT R5). Pivot SIGNAL-ONLY (daemon
  `V10SignalScanner`, Running, zéro capital risqué R10). Fix data risk parity
  (`symbol` 337/337). Tests V10 54/54. HEAD `7a9a7b9`.
  Voir `docs/V10/V10_PHASE_EF_COGNITIVE_REPORT.md`.

### Prochaine étape
Re-calibration seuils V10 sur la lecture TA Søn (Phase I, quand micro dispo) ;
track record Søn (Phase H) ; branchement alerte Telegram du scanner V10.
Valider durable propagation DD protector + risk parity ; promouvoir les SHADOW si WR sain confirmé.

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