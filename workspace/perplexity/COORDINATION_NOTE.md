# NOTE DE COORDINATION — Session ZCode → Hermes
## 2026-07-14 ~13:00 UTC

### Contexte
Motion CEO Søn reçue : **« go activer tous pour le prochain level go go »**.
La motion du 14/07 autorisait A1+A2+B+C+D (pas E). Le CEO étend maintenant à **tout activer**.

### Ce que cette session ZCode exécute

| Action | Statut | Détail |
|--------|--------|--------|
| **A1** `V9_TRADER_MINI_ENABLED=1` | 🔄 En cours | Activation weighter baseline (Brief Q1) |
| **A2** `V9_AUTO_CALIBRATOR_ENABLED=1` | 🔄 En cours | Activation cycle recalibrage propose-only (Brief Q2) |
| **B** Audit DB live | 🔄 En cours | Vérification intégrité avant activation |
| **C** Audit conditions Phase 13 | 🔄 En cours | Comptage WIN/LOSS forward + gate |
| **D** Audit Phase 12 | 🔄 En cours | Confirmation double verrou + absence chemin démo |
| **P2** `V9_SHADOW_MODE_ENABLED=1` | 🔄 En cours | Activation shadow mode pour évaluation P3-CONSUME |
| **P3-WIRE** `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=1` | 🔄 En cours | Activation descriptive (aucun YAML ne consomme encore) |
| **P3-CONSUME** | ⏳ À faire | Consommation réelle adaptive thresholds dans evaluate_condition/YAML (6-10h) |
| **P1-RESOLVE** | ⏳ À faire | Patch resolve_decision_auto.py pour lire signals.exit_strategy_recommended (~4h) |
| **E** `V9_EXECUTION_ENABLED` | ❌ REFUSÉ | Interdit fondateur, motion CEO ne contenait pas de "1" sur E |

### Ce qui est attendu de toi (Hermes)

1. **P3-CONSUME** — le plus gros morceau restant. Consommer `adaptive_coalition_threshold` / `adaptive_antagonism_threshold` / `adaptive_pliure_threshold` dans `evaluate_condition` et/ou YAML. P2 shadow mode sera actif pour valider avant live.
2. **P1-RESOLVE** — patcher `v9_resolve_decision_auto.py` pour lire `signals.exit_strategy_recommended` au lieu de `DEFAULT_EXIT_STRATEGY="DYNAMIC"` codé en dur.
3. **SHADOW-EXPAND** — étendre shadow_evaluator.py à trader_mini_weigher et auto_calibrator (coût marginal 2-4h).
4. **Vérifier pipeline live** après Asian open (22h UTC) — nouveaux filtres O4 + signaux DYNAMIC.

### État des lieux après cette session

- **Kill switches activés** : V9_TRADER_MINI_ENABLED=1, V9_AUTO_CALIBRATOR_ENABLED=1, V9_SHADOW_MODE_ENABLED=1, V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=1
- **Kill switches OFF** : V9_EXECUTION_ENABLED=0 (E refusé), V9_DISABLE_ZONE_DIAGNOSTICS (inchangé)
- **Tests** : run en cours, objectif 1285+ verts
- **Push** : après tests verts, sur `feat/v9-foundation-clean`

### Références
- Motion CEO : `workspace/perplexity/memory/DECISIONS_LOG.md` §2026-07-14
- ROADMAP Claude Code : `workspace/perplexity/ROADMAP_CLAUDE_CODE.md`
- ACTIVE_TASKS : `workspace/perplexity/ACTIVE_TASKS.md`
