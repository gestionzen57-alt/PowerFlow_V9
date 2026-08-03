# ROADMAP V4 — PowerFlow V9 (2026-08-03 07:30+ UTC)

> **Mode CEO no-stop 03/08** : « optimisation max, plein pouvoir, pas
> d'arrêt ». Sprint parallélisé Hermes2 × ZCode2 (2 sessions IA en
> parallèle, chacune avec son périmètre git-indépendant).
>
> **État actuel** : HEAD `83677a2` (pushé origin), 19 commits sprint CEO
> 03/08, 12 leviers L7-L17 quantiques ON, 167 tests verts cumulés.

## Sprint CEO 03/08 — récap final (12 phases livrées)

| Phase | Levier | Owner | Commit |
|---|---|---|---|
| 105 | OOS freeze test STABLE | Hermes | `eb3ef75` |
| 12 | Pyramiding V2 STARS/SUPER_STARS (L10) | Hermes | `603fce7` |
| 03/08 | 7 kill switches CEO ON | Hermes | `45a4dd6` |
| 03/08 | Auto-calibrator 1er run | Hermes | `d5f6692` |
| 03/08 | A11 Audit CVaR | Hermes | `4798467` |
| 03/08 | A16 Audit walk-forward L7/L8/L9 | Hermes | `19179bc` |
| 126 | **L15 Heatmap regime × session × pattern** | Hermes | `c632698` |
| 127 | **L11 GBPUSD × Mer boost + Mar blacklist** | Hermes | `26cd0c6` |
| 03/08 | ROADMAP V3 + 2 prompts ZCode | Hermes | `b01c59b` |
| 03/08 | Skills catalogue V3 (L12+L16) | Hermes | `518872c` |
| 03/08 | A1 Telegram tokens | CEO Søn | `a5e1b22` |
| 130 | **L13 Adaptive TP/SL vol realized** | Hermes | `970a78c` |
| 132 | **Risk Attribution par principe × regime × session** | Hermes | `01cd9f3` |
| 133 | **PyramidingEngine V3 multi-timeframe boost (L17 MTF)** | Hermes | `d7c2d2d` |
| 03/08 | PLAN QUANTIQUE V11+ V3 | Hermes | `2d8e6ca` |
| 128 | **L12 Correlation inter-paires × regime** | **ZCode C1** | `7ed5c55` |
| 134 | **L17 Cross Blacklist GRAMMAR** | Hermes | `7ed5c55` |
| 03/08 | Skills catalogue V3 sprint CEO | Hermes | `f956224` |
| 135 | **Edge Decay Monitor live audit** | Hermes | `749ef61` |
| 03/08 | Bilan CEO sprint | Hermes | `d796dda` |
| 03/08 | Gitignore data/freezes/ | Hermes | `231a576` |
| 129 | **L16 Asymétrie WR par direction** | **ZCode C2** | `83677a2` |

**Bilan** : **22 commits sprint CEO 03/08** (b6424a0 → 83677a2).
- 19 commits Hermes (orchestrateur)
- 1 commit CEO Søn (A1 Telegram en parallèle)
- 2 livraisons ZCode (Phase 128 L12, Phase 129 L16)

**Bénéfice projeté 30j** : **+1988-2688 pips** (L7+L8+L9+L11+L12+L13+L15+L16+L17×2).

---

## ROADMAP V4 — 2 sessions IA en parallèle

### Architecture multi-IA V4 (2 sessions parallèles)

```
┌─────────────────────────────────────────────────────────────────────┐
│                      SPRINT CEO 03/08 (V4)                         │
│                                                                     │
│  HEAD = 83677a2 (origin/feat/v9-foundation-clean, Hermes)         │
│                                                                     │
│  ZCode (M2) livraison Phase 128 L12 ✅ + Phase 129 L16 ✅          │
│  Branche feat/v9-zcode-l16-asymmetry mergée dans foundation-clean.  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
            │                                       │
            │ (chantier A1)                          │ (chantier B1)
            ▼                                       ▼
┌────────────────────────────────┐    ┌──────────────────────────────┐
│  HERMES2 (M3)                  │    │  ZCODE2 (M3)                 │
│  Chantiers Hermes2             │    │  Chantiers ZCode2             │
│  - Phase 136/137/138 (Hermes)  │    │  - Phase 140/141 (ZCode)     │
│  - Branche feat/v9-foundation- │    │  - Branche feat/v9-zcode2-   │
│    clean (push via Hermes2)    │    │    xxx                       │
│  - Push final via Hermes2      │    │  - 0 push, report Hermes2    │
└────────────────────────────────┘    └──────────────────────────────┘
```

### Chantiers git-indépendants V4 (Phase 136-141)

| # | Phase | Owner | Fichiers | Effort | Branche |
|---|---|---|---|---|---|
| **H2-1** | **Phase 136** Pyramid Engine V4 (zones_state) | Hermes2 | `core/v9/v9_pyramiding_engine_v4.py`, `tests/test_v9_pyramiding_engine_v4.py` | 2-3 j | `feat/v9-foundation-clean` |
| **H2-2** | **Phase 137** Adaptive Drawdown Tracker | Hermes2 | `core/v9/v9_adaptive_dd_tracker.py`, `tests/test_v9_adaptive_dd_tracker.py` | 2 j | `feat/v9-foundation-clean` |
| **H2-3** | **Phase 138** Regime Live Detector (DOW × regime × vol) | Hermes2 | `core/v9/v9_regime_live_detector.py`, `tests/test_v9_regime_live_detector.py` | 1-2 j | `feat/v9-foundation-clean` |
| **H2-4** | **Phase 139** ROADMAP V5 + Plan V11+ V4 + Skills catalogue V4 | Hermes2 | `docs/ROADMAP.md`, `docs/audits/PLAN_QUANTIQUE_V11_PLUS_V4_20260803.md`, 2 skills catalogue | 0.5 j | `feat/v9-foundation-clean` |
| **Z2-1** | **Phase 140** L18 Edge Decay Sentinel | ZCode2 | `core/v9/v9_edge_decay_sentinel.py`, `tests/test_v9_edge_decay_sentinel.py`, `core/v9/kill_switches.py` (ajout), `config/v9_kill_switches.env` | 2-3 j | `feat/v9-zcode2-l18-edge-decay` |
| **Z2-2** | **Phase 141** L19 News Shock Attenuator | ZCode2 | `core/v9/v9_news_shock_attenuator.py`, `tests/test_v9_news_shock_attenuator.py`, `core/v9/kill_switches.py` (ajout), `config/v9_kill_switches.env` | 1-2 j | `feat/v9-zcode2-l19-news-shock` |

**Total** : 6 chantiers git-indépendants, **9-11 jours-homme**并行és sur 2 sessions IA.

### Sprint immédiat V4 (lancer en parallèle maintenant)

**ZCode2 démarre Z2-1 ou Z2-2** (au choix, prompt copy-paste ready).

**Hermes2 démarre H2-1 (Phase 136)** pendant que ZCode2 travaille.

### Convergence V4

1. **Hermes2 démarre H2-1 immédiatement** (Phase 136 Pyramid V4).
2. **ZCode2 démarre Z2-1 OU Z2-2** (Phase 140 L18 ou Phase 141 L19).
3. **Hermes2 continue H2-2 (Phase 137)** pendant que ZCode2 livre Z2-1.
4. **Hermes2 H2-3 (Phase 138)** quand H2-2 est commit.
5. **Hermes2 H2-4 (Phase 139 ROADMAP V5 + Plan V4 + Skills V4)** à la fin.
6. **ZCode2 livre Z2-2** (Phase 141) en parallèle.
7. **Hermes2 merge** branches ZCode2 dans feat/v9-foundation-clean.
8. **Hermes2 push final** sur origin (R28 strict).

### Métriques de succès V4

| Métrique | Sprint CEO 03/08 (V3) | Cible V4 |
|---|---|---|
| Leviers quantiques ON | 12 | **17** (+L18+L19+ zones_state+DD tracker) |
| Tests verts | 167 | **240+** |
| Bénéfice projeté 30j | +1988-2688p | **+2600-3200p** |
| Nouveaux kill switches | 12 ON | **17** ON |
| Skills catalogue V9 | 34 | **38+** |
| Commits sprint | 22 | **35+** (22 sprint 03/08 + 13 sprint 03/08+1) |

### Doctrine V4 (inchangée)

- **R7 tests verts** : baseline 167 préservée + ~73 nouveaux = 240+
- **R8 doc** : ROADMAP V5 + PLAN V4 + 4 skills catalogue
- **R14 git vérité** : SQL live pour audits, JAMAIS inventer
- **R22 sous-unité unique** : 1 phase = 1 module + 1 test + 1 commit
- **R25' motion CEO** : kill switches défauts OFF, activation = motion
- **R26 DECISIONS_LOG** : 1 entrée par livraison V4
- **R28 multi-IA** : Hermes2 (orchestrateur), ZCode2 (implémentation),
  CEO Søn (motion)

### Multi-IA V4 (R28)

| Acteur | Rôle | V4 sprint |
|---|---|---|
| **Hermes2 (M3)** | Orchestrateur git unique + implémentation Hermes (H2-1 à H2-4) | 6-8 j commit + push origin |
| **ZCode2 (M3)** | Implémentation branche propre (Z2-1, Z2-2) | 3-5 j commit branche + report |
| **CEO Søn** | Validateur + motion + push parallèle | motions CEO si nécessaires |

**0 conflit git** car :
- Hermes2 = `feat/v9-foundation-clean` (branche principale)
- ZCode2 = `feat/v9-zcode2-*` (branches propres)
- Merge par Hermes2 seul (R28)

---

## Prompts copy-paste ready

Voir fichiers dédiés :
- `workspace/hermes2/PROMPT_PHASE136_PYRAMID_V4.md`
- `workspace/hermes2/PROMPT_PHASE137_DD_TRACKER.md`
- `workspace/hermes2/PROMPT_PHASE138_REGIME_LIVE.md`
- `workspace/hermes2/CONTEXT_HANDBOOK.md` (Hermes2 = héritage Hermes)
- `workspace/zcode2/PROMPT_PHASE140_L18_EDGE_DECAY.md`
- `workspace/zcode2/PROMPT_PHASE141_L19_NEWS_SHOCK.md`
- `workspace/zcode2/CONTEXT_HANDBOOK.md` (héritage ZCode V3)

Lancement parallèle immédiat : CEO copie les 2 prompts dans 2 sessions IA distinctes (Hermes2 + ZCode2).