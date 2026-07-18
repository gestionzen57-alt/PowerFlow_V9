# SKILL — Doctrine V9 (19 règles immuables)

**Version** : 2026-07-18 (resync HEAD 26b0070)

---

## Règles fondatrices (ne jamais violer)

| R# | Règle | Preuve |
|---|---|---|
| R1 | Le code est la source de vérité, pas la doc | DOCGOVERNANCE.md |
| R2 | Chaque couche est additive et filtrante | v9_processus_complet.md |
| R6 | L'orchestrateur ne crash jamais (try/except par couche) | core/v9/orchestrator.py |
| R8 | Documentation mise à jour à chaque PR/commit structurant | DOCGOVERNANCE.md |
| R13 | Le système observe d'abord, agit ensuite (paper réel) | CHARTE_COGNITIVE_V9.md |
| R14 | Le Git courant est la source de vérité, jamais mémoire conversation | README.md |
| R18 | Pas de LLM dans le cœur cognitif (calculs stats purs) | ARCHITECTURE.md |
| R19/TABLE17 | Autonomie agents ne progresse qu'après stabilité live démontrée | ROADMAP.md |
| R22 | 1 périmètre = 1 livraison | DOCTRINE.md |
| R25' | Kill switch ON par motion CEO explicite uniquement | AGENT.md |
| R28 | Hermes = opérateur Git unique | DECISIONS_LOG.md |

## État doctrine 18/07/2026

### Activations récentes (motions CEO explicites)
- **R25' — `V9_GBPUSD_LONG_ONLY=1`** : activé 18/07 matin, motion CEO « neutralise puits baissier »
- **R25' — `V9_PORTFOLIO_RISK_ENABLED=1`** : actif par défaut

### Shadow modes en attente validation (Phase B)
- `V9_BEAR_PERCEPTION_ENABLED=0` → activation si would_skip ≥ 30% sur 60j
- `V9_CONSTITUTIVE_CURRENCY_FILTER=0` → activation si pas de régression sur 60j

### Décisions CEO pendantes
- `V9_POSITION_MANAGER_ENABLED=1` — motion CEO requise (break-even + partial close)
- `V9_MARKET_REGIME_GLOBAL_ENABLED=1` — motion CEO requise (risk-on/off)

### Interdit fondateur (immuable)
- `V9_EXECUTION_ENABLED=0` — exécution réelle jamais, ni Phase 12
- Phase 10 fédération agents : gelée jusqu'à stabilisation live Phase 9

## Anti-patterns à ne jamais faire
- Ouvrir Phase 10 avant stabilisation live confirmée
- Mélanger migration V8→V9 et architecture agents
- Rouvrir un chantier marqué gelé sans motion CEO explicite
- Inventer une structure absente du repo
- Improviser l'état d'un chantier sans lire le Git
