# NOTE DE COORDINATION — Session ZCode ↔ Hermes
## 2026-07-14 ~18:45 UTC — Resync Hermes

### Contexte
Søn en vacances, actif via VPS. Motion CEO « fait ce qu'il faut et continue les activation ».
**Fable hors service** (pas de crédit) — ZCode et Hermes continuent en parallèle sur
`feat/v9-foundation-clean`. Session Søn parallèle à venir via ZCode (à coordonner ici).

### État actuel (2026-07-14 ~18:45 UTC)

| Action | Statut | Qui | Détail |
|--------|--------|-----|--------|
- **A1** `V9_TRADER_MINI_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **A2** `V9_AUTO_CALIBRATOR_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **P2** `V9_SHADOW_MODE_ENABLED=1` | ✅ Fait | ZCode | Commit `5049d48` |
| **P3-WIRE** `V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED` | ✅ ON | ZCode+Hermes | Activé 14/07 commit `ac26c3a` (motion CEO priorité 3) — §2.4 DECISIONS_LOG 15/07 |
| **B+C+D** Audits | ✅ Fait | ZCode | DB 1.56GB, 9516 résolues, gate R30 PASS |
| **DB restoration** | ✅ Fait | Hermes | Commit `2ab07f3` (DB drainée → restaurée) |
| **Wrapper kill switches** | ✅ Fait | Hermes | Commit `2ab07f3` (loader .py + .bat + conftest) |
| **P1-RESOLVE** | ✅ Fait | ZCode | `resolve_one()` lit `signals.exit_strategy_recommended` — 3 nouveaux tests, 36/36 verts |
| **SHADOW-EXPAND** | 🔄 En cours | ZCode | Étendre shadow_evaluator à trader_mini_weigher + auto_calibrator |
| **P3-CONSUME** | ✅ **LIVRÉ 2026-07-14 18:55 UTC** | Hermes | 3 commits distants `f13c10f`/`eb1e7b9`/`01c2b9d`. 27 _ADAPTIVE générés (1 P3-CONSUME + 26 P3-CONSUME-EXTEND), tests 1303 verts. |
| **P3-CONSUME-EXTEND — CLOS** | ✅ **CLOSED 2026-07-15** | Hermes | §2.2 DECISIONS_LOG — bilan, baseline 1307 verts (ajd +4), tous SHADOW. Promotion ACTIVE = motion CEO distincte. |
| **Boucle apprentissage** | ✅ **Activée** | Hermes | Cron `V9_LearningLoop` installé Ready (18:43 UTC). Arbitrage §2.1 15/07 : 5 PENDING → 2 APPROVED (`cf7955b1be08` haussière, `49f65b2cb806` baissière) + 3 REJECTED (doublons). 0 PENDING. |
| **Resync docs** | ✅ Fait | Hermes | Commit `f94d2a9` + `48ea826` + `f13c10f` + `eb1e7b9` + `01c2b9d` — 5 docs resyncés + CHANGELOG étendu |
| **TP_SL P3-D1** | ❌ **CLOSED-OBSOLETE 2026-07-15** | — | §2.3 DECISIONS_LOG — 0 cas TP_SL depuis P1-RESOLVE. Tâche historique neutralisée. |
| **Phase 14 SPECIFIQUE** | ✅ **LIVRÉ 2026-07-15 05:25 UTC** | Hermes | §3 DECISIONS_LOG — `b7bfc98` poussé origin. Module `learning_offset_applier` + wire-up arbiter + CLI + 23 tests. Kill switch `V9_LEARNING_OFFSET_ENABLED` OFF par défaut, activation = motion CEO distincte. |
| **Push** | ✅ **PUSHÉ 2026-07-15 05:05 UTC** | Hermes | PAT fourni par Søn via chat (modèle mémoire). `ac26c3a..f4e1798` → origin/feat/v9-foundation-clean. A redemander par session (credential store bash non persistant). |
| **Phase 14 push** | ✅ **PUSHÉ 2026-07-15 05:25 UTC** | Hermes | `587ca7c..b7bfc98` → origin/feat/v9-foundation-clean. Suite à motion CEO « fait la phase 14 et tout ». |
| **E** `V9_EXECUTION_ENABLED` | ❌ REFUSÉ | — | Interdit fondateur |
| **WIRE activation** | ✅ **FAIT 14/07** | ZCode+Hermes | cf. ligne P3-WIRE — activation = `ac26c3a` |
| **Arbitrage 5 propositions learning_loop** | ✅ **FAIT 2026-07-15 05:00 UTC** | Hermes | §2.1 DECISIONS_LOG — meilleur haussier + meilleur baissier 30j APPROVED, 3 doublons REJECTED. |

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
- Dernier commit distant : `b7bfc98` (Phase 14 livraison, 15/07 ~05:25 UTC)
- Session §3 2026-07-15 : Phase 14 SPECIFIQUE livrée (module learning_offset_applier + wire-up arbiter + CLI + 23 tests)
- Avant : `587ca7c` (note push §2)
- Avant : `f4e1798` (docs §2.1-2.5 arbitrage learning_loop + clôture P3-CONSUME-EXTEND)
- Avant : `ac26c3a` (priorité 3 14/07 — WIRE ON + dashboard HITL + shadow evaluateur)
- Avant : `01c2b9d` (P3-CONSUME-EXTEND COMPLET, Hermes)
- Avant : `f13c10f` (groupe 1 node_rule) / `eb1e7b9` (groupe 2 birth/break)
- Avant : `f94d2a9` (resync 18:25)
- Avant : `149f3b0` (7e MCP server)
- DECISIONS_LOG : `workspace/perplexity/memory/DECISIONS_LOG.md`
- Tests baseline : **1330 verts + 1 skipped + 0 fail** (2:30, baseline 1307 + 23 Phase 14)
