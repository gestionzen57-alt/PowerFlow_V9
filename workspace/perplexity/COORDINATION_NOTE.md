# NOTE DE COORDINATION — Session ZCode ↔ Hermes
## 2026-07-14 ~18:45 UTC — Resync Hermes

### Contexte
Søn en vacances, actif via VPS. Motion CEO « fait ce qu'il faut et continue les activation ».
**Fable hors service** (pas de crédit) — ZCode et Hermes continuent en parallèle sur
`feat/v9-foundation-clean`. Session Søn parallèle à venir via ZCode (à coordonner ici).

### État actuel (2026-07-14 ~18:45 UTC)

| Action | Statut | Qui | Détail |
|--------|--------|-----|--------|
| **A1** `V9_TRADER_MINI_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **A2** `V9_AUTO_CALIBRATOR_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **P2** `V9_SHADOW_MODE_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **P3-WIRE** `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED` | ⏸ OFF | — | R25' strict — activation = motion CEO distincte |
| **B+C+D** Audits | ✅ Fait | ZCode | DB 1.56GB, 9516 résolues, gate R30 PASS |
| **DB restoration** | ✅ Fait | Hermes | Commit `2ab07f3` (DB drainée → restaurée) |
| **Wrapper kill switches** | ✅ Fait | Hermes | Commit `2ab07f3` (loader .py + .bat + conftest) |
| **P1-RESOLVE** | ✅ Fait | ZCode | `resolve_one()` lit `signals.exit_strategy_recommended` — 3 nouveaux tests, 36/36 verts |
| **SHADOW-EXPAND** | 🔄 En cours | ZCode | Étendre shadow_evaluator à trader_mini_weigher + auto_calibrator |
| **P3-CONSUME** | ✅ **LIVRÉ 2026-07-14 18:55 UTC** | Hermes | 3 commits distants `f13c10f`/`eb1e7b9`/`01c2b9d`. 27 _ADAPTIVE générés (1 P3-CONSUME + 26 P3-CONSUME-EXTEND), tests 1303 verts. |
| **Boucle apprentissage** | ✅ **Activée** | Hermes | Cron `V9_LearningLoop` installé Ready (18:43 UTC). 2 propositions PENDING générées (haussière 93% WR n=6228, baissière 65% WR n=1843). cognitive_journal: 7 rows (5 meta_agent + 2 auto_calibrator aujourd'hui) |
| **Resync docs** | ✅ Fait | Hermes | Commit `f94d2a9` + `48ea826` + `f13c10f` + `eb1e7b9` + `01c2b9d` — 5 docs resyncés + CHANGELOG étendu |
| **E** `V9_EXECUTION_ENABLED` | ❌ REFUSÉ | — | Interdit fondateur |
| **WIRE activation** | ❌ En attente motion CEO | — | R25' strict — Søn tranchera |

### Hand-off mis à jour

**Fable hors service** (pas de crédit). P3-CONSUME-EXTEND **repris par Hermes**
(mandat CEO « fait ce qu'il faut »). Fable 5 = clos sans livraison.

**ZCode en parallèle** : continue SHADOW-EXPAND sur sa session, livre ses commits
sur `feat/v9-foundation-clean` sans marcher sur P3-CONSUME-EXTEND (périmètre Hermes).

**Périmètre ZCode** (cette session parallèle) :
- SHADOW-EXPAND (en cours)
- Mise à jour ACTIVE_TASKS.md + BOARD.md (sa copie si besoin)
- Tests → commit → push (R28 motion CEO implicite « push et donne plan d'action »)

**Périmètre Hermes** (cette session) :
- ✅ P0+P1+P2 resync faits (commit `f94d2a9`)
- ✅ Boucle apprentissage activée (cron installé, 2 propositions générées)
- 🔄 P3-CONSUME-EXTEND — livraison prochaine (6-10h, 26 principes)
- Aligner COORDINATION_NOTE.md à chaque jalon pour ZCode

### Références
- Dernier commit distant : `01c2b9d` (P3-CONSUME-EXTEND COMPLET, Hermes)
- Avant : `f13c10f` (groupe 1 node_rule) / `eb1e7b9` (groupe 2 birth/break)
- Avant : `f94d2a9` (resync 18:25)
- Avant : `149f3b0` (7e MCP server)
- DECISIONS_LOG : `workspace/perplexity/memory/DECISIONS_LOG.md`
- Tests baseline : **1303 verts + 2 skipped + 0 fail** (3:36)
