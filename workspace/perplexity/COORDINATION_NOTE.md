# NOTE DE COORDINATION — Session ZCode ↔ Hermes
## 2026-07-14 ~14:00 UTC

### Contexte
Motion CEO Søn : **« go activer tous pour le prochain level go go »**.
Travail en parallèle ZCode + Hermes sur `feat/v9-foundation-clean`.

### État actuel (2026-07-14 ~14:00 UTC)

| Action | Statut | Qui | Détail |
|--------|--------|-----|--------|
| **A1** `V9_TRADER_MINI_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **A2** `V9_AUTO_CALIBRATOR_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **P2** `V9_SHADOW_MODE_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **P3-WIRE** `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **B+C+D** Audits | ✅ Fait | ZCode | DB 1.56GB, 9516 résolues, gate R30 PASS |
| **DB restoration** | ✅ Fait | Hermes | Commit `2ab07f3` (DB drainée → restaurée) |
| **Wrapper kill switches** | ✅ Fait | Hermes | Commit `2ab07f3` (loader .py + .bat + conftest) |
| **P1-RESOLVE** | ✅ Fait | **ZCode** | `resolve_one()` lit `signals.exit_strategy_recommended` — 3 nouveaux tests, 36/36 verts |
| **SHADOW-EXPAND** | 🔄 En cours | ZCode | Étendre shadow_evaluator à trader_mini_weigher + auto_calibrator |
| **P3-CONSUME** | ⏳ À faire | Hermes | Consommation réelle adaptive thresholds dans evaluate_condition/YAML (6-10h) |
| **E** `V9_EXECUTION_ENABLED` | ❌ REFUSÉ | — | Interdit fondateur |

### Hand-off mis à jour

**P1-RESOLVE a été pris par ZCode** (commit en cours). Hermes peut se concentrer sur **P3-CONSUME** uniquement — c'est le plus gros morceau restant.

**Périmètre ZCode** (cette session) :
- SHADOW-EXPAND (en cours)
- Mise à jour ACTIVE_TASKS.md + BOARD.md
- Tests → commit → push

**Périmètre Hermes** (session parallèle) :
- P3-CONSUME (HAUTE, 6-10h) — consommation réelle adaptive thresholds
- Vérification pipeline live (Asian open 22h UTC)

### Références
- Dernier commit ZCode : `5049d48` (activation générale)
- Dernier commit Hermes : `2ab07f3` (DB restoration + wrapper)
- DECISIONS_LOG : `workspace/perplexity/memory/DECISIONS_LOG.md`
