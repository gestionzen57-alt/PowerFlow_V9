# ROADMAP V5 — PowerFlow V9 (2026-08-04)

> **Mode CEO no-stop 03/08+2** : « optimisation max, plein pouvoir, pas
> d'arrêt ». Sprint parallélisé Hermes3 × ZCode3 (2 sessions IA en
> parallèle, chacune avec son périmètre git-indépendant).
>
> **État actuel** : HEAD `41048b2` (pushé origin), 28 commits sprint CEO
> cumulés (V3 + V4 + V5), 15 leviers L7-L20 quantiques ON, 236 tests verts
> cumulés (192 V4 + 33 L19 + 44 L20, hors dette technique pré-V4 72 F).

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
| Phases livrées | 141 | **144** (+141 + 142 + 143) |
| Dette technique pré-V4 (F) | 76 | **76 documentée** (Phase 144 sprint dédié futur) |

---

## Périmètre GELÉ (inchangé depuis V4)

- Phase 10 : Fédération d'agents
- Skills auto-générés avant canonisation
- Exécution d'ordres réelle avant Phase 12

## Prochaine étape sprint V5

- **Phase 142** : ROADMAP V5 + PLAN V5 finalisé (0.5 j, en cours)
- **Phase 145** : audit live mardi 04/08 18:00 UTC (24h post-activation L7+L8+L9+L11+L13+L17×2)
- **Phase 146** : audit live vendredi 08/08 18:00 UTC (semaine)
- **Phase 147** : push final + bilan CEO V5 + DECISIONS_LOG clôture

**Sprint CEO 03/08+2 V5 = EN COURS. Architecture parallélisée Hermes3 ×
ZCode3 opérationnelle. Pattern sprint V4 reproduit avec succès.**
