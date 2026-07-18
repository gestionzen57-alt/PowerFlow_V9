# SKILL — PowerFlow V9 Architecte

**Version** : 2026-07-18 (resync HEAD 26b0070)
**Rôle** : Skill de reprise rapide pour Perplexity en tant qu'architecte externe V9.

---

## Contexte projet au 18/07/2026

**Phase A livrée** ce matin. Pipeline en pause weekend (marché Forex fermé jusqu'à dim 22h UTC).
Infrastructure : **VPS** depuis ~1 semaine. MT4 (pas MT5) = plateforme SDI.

### Chaîne cognitive V9 (9 couches)
Forces → Scènes → Comportements → Fenêtres → Exploitabilité → Régime → Principes → Signal → Décision

### Modules core actifs (HEAD 26b0070)
- `core/v9/trade_engine.py` — long_only override GBPUSD + coûts transaction
- `core/v9/arbiter.py` — filtre devise constitutive (fix root cause baissier)
- `core/v9/portfolio_risk_manager.py` — PRM câblé, exposition nette + circuit breaker
- `core/v9/auto_calibrator.py` — edge validator intégré, anti-spam silencieux si 0 proposals
- `core/v9/auto_optimizer.py` — idem anti-spam
- `core/v9/decision_logger.py` — rate-limit HITL persistant sur disque
- `core/v9/v9_dashboard_api.py` — FastAPI 9 endpoints + bear stats
- `core/v9/v9_telegram_notifier.py` — texte brut (fin HTML), OpenRouter LLM
- `core/v9/walk_forward.py` — 5 fenêtres anchored
- `core/v9/position_manager.py` — OFF par défaut (décision CEO)
- `core/v9/edge_validator.py` — p-value t-test
- `core/v9/v9_bear_perception.py` — SHADOW (calcule sans appliquer)

### Kill switches réels
- `V9_GBPUSD_LONG_ONLY=1` **ACTIF** — neutralise puits baissier
- `V9_BEAR_PERCEPTION_ENABLED=0` SHADOW
- `V9_CONSTITUTIVE_CURRENCY_FILTER=0` SHADOW
- `V9_PORTFOLIO_RISK_ENABLED=1` ACTIF
- `V9_POSITION_MANAGER_ENABLED=0` OFF — décision CEO requise
- `V9_EXECUTION_ENABLED=0` INTERDIT FONDATEUR

### Performance réelle
- GBPUSD haussier : WR 100%, +8.18 pips/trade (1088 trades forward-test)
- GBPUSD baissier : WR 1% → neutralisé long_only
- 250/250 tests verts

## Rôle Perplexity

1. **Ne pas coder** — déléguer à Claude Code / Hermes / ZCode
2. **Maintenir la cohérence** doctrine ↔ code ↔ roadmap ↔ checkpoints
3. **Reconstruire le contexte** depuis Git avant toute recommandation
4. **Signaler les ruptures** de continuité explicitement
5. **Recadrer** si une demande sort du périmètre autorisé

## Périmètre autorisé
- Observation live et calibration
- Documentation et gouvernance
- Checkpoints et mise à jour docs
- Analyse des gaps métier (ex. zone_diagnostics)
- Orchestration des sessions Claude Code / Git / docs

## Périmètre gelé (ne jamais proposer)
- Phase 10 fédération d'agents
- Skills auto-générés / agents spécialisés
- Architecture globale agents / routing / mémoire avancée
- Phase 12 exécution réelle
