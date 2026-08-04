# V10 STATE — État du pipeline cognitif V10

**Dernière mise à jour** : 2026-08-04 (~22:00 UTC) — autopilot Hermes
**Branche active** : `feat/v9-foundation-clean`
**HEAD courant** : `c9fed1c` (Phase 1d demo)

---

## ✅ Phases livrées

### Phase E-F — Cœur cognitif V10 (commits `80ed319` → `00e5f1a`)
- `core/v10/v10_force.py` — F1-F5 (5 features de pression/volume/spread)
- `core/v10/v10_structure.py` — S1-S9 (structures chart : BOS, FVG, OB, etc.)
- `core/v10/v10_context.py` — C1-C7 (session/news/range/vol regime)
- `core/v10/v10_orchestrator.py` — compose → V10 Signal A1/A2/A3/NONE + CoT R5
- 54/54 tests verts cumulés

### EDGE FUND Phase 1 — Currency Strength Engine (commits `b1c3b98` → `c9fed1c`)
- `core/v10/v10_currency_pairs.py` — INVERSION_MAP (6 paires × 2 devises), 7 devises agrégées
- `core/v10/v10_currency_strength.py` — moteur Fatman Hawkeye par devise
- 4 + 12 = **16 nouveaux tests verts** (cumul V10 : 70/70)
- `scripts/v10_currency_strength_demo.py` — CLI validation DB live
- 0 capital risqué (R10)

---

## 🔄 Phases en cours / à venir

| Phase | Module | Statut | Priorité |
|---|---|---|---|
| 1 | Currency Strength | ✅ Livré | — |
| 2 | VSA Engine | 🔴 À démarrer | 🔴 P1 |
| 3 | Extreme Detector | 🔴 À démarrer | 🔴 P2 |
| 4 | Multi-TF Confluence | ⏸️ En attente Phase 2 | P3 |
| 5 | Signal Orchestrator V10 | ⏸️ En attente Phase 4 | P4 |
| 6 | MT5 Bridge Tickmill | ⏸️ En attente Phase 5 | P5 |
| 7 | Macro Filter (COT) | ⏸️ En attente Phase 4 | P6 |
| 8 | Scalp Engine M1 | ⏸️ En attente Phase 5 | P7 |

---

## 📊 Métriques live (snapshot H1 — 2026-08-04T20:00 UTC)

| Devise | Score | Rank |
|---|---|---|
| GBP | 95.00 | 1 |
| JPY | 95.00 | 2 |
| EUR | 5.00 | 3 |
| USD | 5.00 | 4 |
| CHF | 5.00 | 5 |
| AUD | 5.00 | 6 |
| CAD | 5.00 | 7 |

Spread Fatman : 90.00 (signal de forte divergence devise — observable cross-pair).

> **Note d'étalonnage** : la fenêtre `history` est synthétique pour Phase 1.
> Sera réinjectée en Phase 2 (VSA) et étalonnée en Phase 7 (Macro) pour
> des scores reflétant le momentum réel sur fenêtre 50.

---

## 🎯 Doctrine V10 respectée

- **R1-AGIR** : mode autopilote, exécution sans permission CEO micro
- **R2 additif** : 0 modification core/v9/, tout dans core/v10/
- **R6 fail-open** : data insuffisante → score=50 neutre, log warning
- **R7 tests verts** : 70/70 cumulés (54 V10 + 16 Edge Fund Phase 1)
- **R9 auditable** : seed reproductible, métadonnées sérialisées, JSON output
- **R10 capital protégé** : 0 ordre réel, compute only

---

## 🔗 Liens

- Plan : `docs/V10/V10_PLAN_REPARALETTRAGE.md`
- Edge Fund Quantique : `docs/V10/V10_PLAN_EDGE_FUND_QUANTIQUE.md`
- Coeur cognitif : `docs/V10/V10_PHASE_EF_COGNITIVE_REPORT.md`
- Phase 1 Edge Fund : `docs/V10/V10_PHASE_EDGE_FUND_PHASE1_REPORT.md` (à venir Commit 6)
- AGENTS.md : doctrine + rituels
- SOUL.md : âme du système
- DECISIONS_LOG : `workspace/perplexity/memory/DECISIONS_LOG.md`
