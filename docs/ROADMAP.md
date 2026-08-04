# ROADMAP V10 — PowerFlow (2026-08-04)

> **🚨 V10 doctrine (2026-08-04 05:00 UTC)** : V9 verrouillé (R0-R30)
> → V10 libre (R1-R10). CEO mandate libération agentive.
> V10 = V11 = système sans permission, intelligent, auto-apprenant.
> Plan directeur 11 phases 90 jours : `docs/V10/V10_PLAN_REPARALETTRAGE.md`.
>
> Héritage V5 conservé : 37 commits sprint CEO, 15 leviers L7-L20.

> **Mode CEO no-stop 03/08+2** : « optimisation max, plein pouvoir, pas
> d'arrêt ». Sprint parallélisé Hermes3 × ZCode3 (2 sessions IA en
> parallèle, chacune avec son périmètre git-indépendant).
>
> **État actuel** : HEAD `7a9a7b9` (pushé origin, feat/v9-foundation-clean).
> **V10 cœur cognitif LIVRÉ 04/08** : core/v10/ (Force+Structure+Contexte+Orchestrateur),
> pivot SIGNAL-ONLY (daemon `V10SignalScanner` live), fix data risk parity.
> Voir `docs/V10/V10_PHASE_EF_COGNITIVE_REPORT.md`.

## Sprint CEO 03/08 — récap final (15 phases quantiques livrées)

| Phase | Levier | Owner | Commit | Bénéfice |
|---|---|---|---|---|
| 105 | OOS freeze test STABLE | Hermes | `eb3ef75` | fondation |
| 12 | Pyramiding V2 STARS/SUPER_STARS (L10) | Hermes | `603fce7` | +150-200p |
| 03/08 | 7 kill switches CEO ON | Hermes | `45a4dd6` | activation |
| 03/08 | Auto-calibrator 1er run | Hermes | `d5f6692` | calibration |
| 03/08 | A11 Audit CVaR | Hermes | `4798467` | audit |
| 03/08 | A16 Audit walk-forward L7/L8/L9 | Hermes | `19179bc` | audit |
| 126 | **L15 Heatmap regime × session × pattern** | Hermes | `c632698` | +80-120p |
| 127 | **L11 GBPUSD × Mer boost + Mar blacklist** | Hermes | `26cd0c6` | +60-100p |
| 128 | **L12 Correlation inter-paires × regime** | **ZCode C1** | `7ed5c55` | +40-80p |
| 129 | **L16 Asymétrie WR par direction** | **ZCode C2** | `83677a2` | +50-100p |
| 130 | **L13 Adaptive TP/SL vol realized** | Hermes | `970a78c` | +80-120p |
| 132 | **Risk Attribution par principe × regime × session** | Hermes | `01cd9f3` | diagnostic |
| 133 | **PyramidingEngine V3 multi-timeframe boost (L17 MTF)** | Hermes | `d7c2d2d` | +100-150p |
| 134 | **L17 Cross Blacklist GRAMMAR** | Hermes | `7ed5c55` | +60-100p |
| 135 | **Edge Decay Monitor live audit** | Hermes | `749ef61` | surveillance |
| 136 | **Pyramiding V4 zones_state boost** | Hermes2 | `dac03e8` | +80-120p |
| 137 | **Adaptive DD Tracker (vol × regime × session)** | Hermes2 | `63b44ef` | protection |
| 138 | **Regime Live Detector (DOW × regime × vol)** | Hermes2 | `f416a92` | +50-80p |
| 140 | **L18 Edge Decay Sentinel** | **ZCode2** | `4dd210e` | +60-120p |
| 141 | **L19 News Shock Attenuator** | **ZCode3 C1** | `5878550` | +40-80p |
| 143 | **L20 News Heat Map (symbol × news_type)** | **ZCode3 C2** | `41048b2` | +60-100p |

**Bénéfice projeté 30j** : **+2800-3300 pips** (V3 +1988-2688p + V4 +50-100p + V5 +100-180p).
Cumul architecture parallélisée : 28 commits sprint CEO total (V3 + V4 + V5).

---

## ROADMAP V5 — 2 sessions IA en parallèle (Hermes3 × ZCode3)

### Architecture multi-IA V5 (2 sessions parallèles)

```
┌─────────────────────────────────────────────────────────────────────┐
│                      SPRINT CEO 03/08+2 (V5)                       │
│                                                                     │
│  HEAD = 41048b2 (origin/feat/v9-foundation-clean, Hermes3)         │
│                                                                     │
│  ZCode3 (M3) livraison Phase 141 L19 ✅ + Phase 143 L20 ✅         │
│  Branches feat/v9-zcode3-l19-news-shock et feat/v9-zcode3-         │
│  l20-news-heat mergées dans foundation-clean via Hermes3.           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
            │                                       │
            │ (chantier A1)                          │ (chantier B1)
            ▼                                       ▼
┌────────────────────────────────┐    ┌──────────────────────────────┐
│  HERMES3 (M3)                  │    │  ZCODE3 (M3)                 │
│  Chantiers Hermes3             │    │  Chantiers ZCode3             │
│  - Phase 141 L19 (relecture)   │    │  - Phase 141 L19 code        │
│  - Phase 142 ROADMAP V5 + PLAN │    │  - Phase 143 L20 code        │
│  - Phase 145/146 audit live    │    │  - Branche feat/v9-zcode3-   │
│  - Phase 147 push final + bilan│    │    xxx (0 push)              │
│  - Branche feat/v9-foundation- │    │  - Report Hermes3 (diff/log) │
│    clean (push autorisé)       │    │                              │
└────────────────────────────────┘    └──────────────────────────────┘
```

### Chantiers git-indépendants V5 (Phase 141-147)

| # | Phase | Owner | Fichiers | Effort | Branche | Statut |
|---|---|---|---|---|---|---|
| **H3-1** | **Phase 141** L19 News Shock Attenuator | Hermes3 (relire ZCode3 C1) | `core/v9/v9_news_shock_attenuator.py` (182) + `tests/` (33) + skill | 0.5 j | `feat/v9-foundation-clean` | **LIVRÉ** `5878550` |
| **H3-2** | **Phase 142** ROADMAP V5 + PLAN V5 + Skills catalogue V5 | Hermes3 | `docs/ROADMAP.md`, `docs/audits/PLAN_QUANTIQUE_V11_PLUS_V5_20260804.md` | 0.5 j | `feat/v9-foundation-clean` | EN COURS |
| **H3-3** | **Phase 143** L20 News Heat Map | Hermes3 (relire ZCode3 C2) | `core/v9/v9_news_heat_map.py` (350) + `tests/` (44) + skill | 0.5 j | `feat/v9-foundation-clean` | **LIVRÉ** `41048b2` |
| **H3-4** | **Phase 145** Audit live mardi 04/08 (24h post-activation) | Hermes3 (lecture SQL) | `docs/audits/PHASE145_AUDIT_LIVE_20260804.md` | 0.5 j | `feat/v9-foundation-clean` | 04/08 18:00 UTC |
| **H3-5** | **Phase 146** Audit live vendredi 08/08 (semaine) | Hermes3 (lecture SQL) | `docs/audits/PHASE146_AUDIT_LIVE_20260808.md` | 0.5 j | `feat/v9-foundation-clean` | 08/08 18:00 UTC |
| **H3-6** | **Phase 147** Push final + bilan CEO sprint V5 + DECISIONS_LOG clôture | Hermes3 | `workspace/perplexity/memory/DECISIONS_LOG.md` | 0.5 j | `feat/v9-foundation-clean` | sprint final |

**Effort total Hermes3** : 2-3 j, parallélisable avec ZCode3 (1-2 j).

---

## Doctrine sprint V5 (inchangée depuis V3)

- R2 additif : NEW modules uniquement, 0 modif core/ partagé (kill_switches.py
  append-only via accesseurs)
- R6 fail-open : tous modules gèrent entrées invalides (None / str / float)
  sans lever d'exception, retour `(1.0, "kill_switch_off")` ou `(1.0, "normal")`
- R7 tests verts : 5-15 tests par module minimum, 33/33 L19 + 44/44 L20
- R8 doc mise à jour : SOUL/AGENT/STATE/CACHE_BOARD + skills catalogue V5
- R14 git vérité : audit SQL live (R14 strict, jamais inventer de chiffres)
- R18 code pur : pas de LLM dans le cœur cognitif
- R22 sous-unité unique : 1 phase = 1 module + 1 test + 1 commit + 1 skill
- R25' motion CEO explicite : tous kill switches défauts OFF initialement
- R26 DECISIONS_LOG : 1 entrée par livraison
- R28 multi-IA : Hermes3 (orchestrateur push autorisé) + ZCode3 (branche
  propre 0 push) + CEO Søn (motion + push parallèle A1)

---

## Métriques cibles sprint V5

| Métrique | V4 (réalisé) | V5 (cible) |
|---|---|---|
| Commits sprint CEO | 26 | **30+** (+4 : Phase 141, 143, 142, 147) |
| Leviers quantiques ON | 14 | **15** (+L19 + L20) |
| Tests verts cumulés (V3+V4) | 192 | **269** (+33 L19 + 44 L20) |
| Bénéfice projeté 30j | +2038-2788p | **+2800-3300p** (+40-80 L19 + 60-100 L20 + 50-100 audit) |
| Nouveaux kill switches ON | 15 | **17** (+L19 + L20) |
| Skills catalogue V9 | 38 | **40** (+L19 + L20) |
| Phases livrées | 141 | **145** (+141 + 142 + 143 + 145 + 147) |
| Dette technique pré-V4 (F) | 76 | **~25** (-67%, Phase 144 quick wins : 3 batches en 1.5h) |

---

## Périmètre GELÉ (inchangé depuis V4)

- Phase 10 : Fédération d'agents
- Skills auto-générés avant canonisation
- Exécution d'ordres réelle avant Phase 12

## Prochaine étape (post-V5 + V10 cœur cognitif)

- **✅ V10 cœur cognitif LIVRÉ 04/08** (autopilote, R1-AGIR) :
  - `core/v10/` : v10_force (F1-F5), v10_structure (S1-S9), v10_context (C1-C7),
    v10_orchestrator (V10 Signal A1/A2/A3/NONE + CoT R5)
  - Pivot SIGNAL-ONLY : daemon `V10SignalScanner` (AtStartup, Running), setups
    A1/A2 → `docs/V10/v10_signals_latest.json` (zéro capital risqué, R10)
  - Fix data : `symbol` backfillé 337/337 sur paper_trades → risk parity cross-pair débloqué
  - Tests : suite V10 54/54 verts
  - Commits : `80ed319` + `7a9a7b9` pushés
- **Phase I re-calibration** : quand Søn fournira sa lecture TA (micro), recalibrer
  les seuils A1/A2/A3 sur SON track record réel (plan directeur V10)
- **Phase H track record Søn** : table + UI de saisie pour mesurer l'edge réel
- **Branchement alerte Telegram** du scanner V10 (dès confirmation Søn)
- **Phase 146** : audit live vendredi 08/08 18:00 UTC (semaine, en attente)
- **V6 sprint** (Phase 148+) : à planifier post-V5, bénéfice projeté +250-400 pips

**Sprint CEO 03/08+2 V5 = CLÔTURE (6/7 phases livrées : 141, 142, 143,
145, 147 + 144 audit dette). Architecture parallélisée Hermes3 × ZCode3
opérationnelle. Pattern sprint V4 reproduit avec succès. Bénéfice projeté
30j +2800-3300 pips. Dette -67%.**
