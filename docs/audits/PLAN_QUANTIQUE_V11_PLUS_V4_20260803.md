# PLAN QUANTIQUE V11+ V4 — PowerFlow V9 (2026-08-03 07:30 UTC)

> **Sprint CEO 03/08 V3 → V4** : ZCode a livré ses 2 prompts (Phase 128 L12
> + Phase 129 L16). Sprint CEO 03/08 finalisé : **22 commits** pushés,
> **12 leviers L7-L17 quantiques ON**, **167 tests verts**.

## Sprint CEO 03/08 — récap V3 final (12 phases livrées)

### ✅ Phases livrées sprint CEO 03/08 (12 phases)

| Phase | Levier | Owner | Gain | Statut |
|---|---|---|---|---|
| 105 | OOS freeze test STABLE | Hermes | A2 DB OK | ✅ |
| 12/03/08 | PyramidingEngine V2 STARS/SUPER_STARS (L10) | Hermes | x1.3/x1.5 | ✅ |
| 03/08 | 7 kill switches CEO ON (motion) | Hermes | A5-A12 | ✅ |
| 03/08 | Auto-calibrator premier run | Hermes | R30 boucle | ✅ |
| 126 | **L15 Heatmap regime × session × pattern** | Hermes | +200-400p | ✅ |
| 127 | **L11 GBPUSD × Mer boost + Mar blacklist** | Hermes | +100-200p | ✅ |
| 128 | **L12 Correlation inter-paires × regime** | **ZCode C1** | +80-150p | ✅ |
| 129 | **L16 Asymétrie WR par direction** | **ZCode C2** | +100-250p | ✅ |
| 130 | L13 Adaptive TP/SL vol realized | Hermes | +50-100p | ✅ |
| 132 | Risk Attribution par principe × regime × session | Hermes | analytics | ✅ |
| 133 | L17 Pyramiding V3 multi-timeframe boost | Hermes | +30-60p | ✅ |
| 134 | L17 Cross Blacklist GRAMMAR*REJET*asie | Hermes | +150-300p | ✅ |

### Métriques sprint CEO 03/08

| Métrique | Valeur |
|---|---|
| **Commits sprint** | 22 (b6424a0 → 83677a2) |
| **Commits Hermes** | 19 (orchestrateur) |
| **Commits CEO Søn** | 1 (A1 Telegram) |
| **Livraisons ZCode** | 2 (Phase 128 + Phase 129) |
| **Tests verts cumulés** | **167** (sprint CEO 03/08, 14 fichiers) |
| **Leviers quantiques ON** | **12** (L7+L8+L9+L10+L11+L12+L13+L16+L17×2 + L15 partiel) |
| **Bénéfice projeté 30j** | **+1988-2688 pips** (vs 1278p baseline) |
| **Nouveaux kill switches** | 12 ON + 4 switches adaptatifs L15 |
| **Skills catalogue V9** | 34 (Phase 126-129 + sprint CEO 03/08) |
| **MCP servers** | 15 registered + 1 helper stdio |
| **Phases livrées** | **135** (Phase 126-135 + Phase 128 ZCode + Phase 129 ZCode) |

## Plan V11+ V4 — sprint CEO 03/08+1 (parallélisé Hermes2 × ZCode2)

### 🚧 À lancer — 6 phases parallélisées V4

#### Hermes2 (4 phases)

1. **Phase 136 — Pyramid Engine V4 (zones_state boost)**
   - Effort : 2-3 j | Gain : 50-100p
   - Extension V3 : intègre zones_state (zone naissance/2e_jambe/retest/range)
   - Code : `core/v9/v9_pyramiding_engine_v4.py` + tests
   - Branche : `feat/v9-foundation-clean`

2. **Phase 137 — Adaptive Drawdown Tracker**
   - Effort : 2 j | Gain : 80-150p
   - Tracker DD adaptatif par contexte (vol × regime × session)
   - Code : `core/v9/v9_adaptive_dd_tracker.py` + tests
   - Branche : `feat/v9-foundation-clean`

3. **Phase 138 — Regime Live Detector (DOW × regime × vol)**
   - Effort : 1-2 j | Gain : 40-80p
   - Détecteur régime live combinant DOW + regime + volatilité
   - Code : `core/v9/v9_regime_live_detector.py` + tests
   - Branche : `feat/v9-foundation-clean`

4. **Phase 139 — ROADMAP V5 + PLAN V4 + Skills catalogue V4 (clôture sprint)**
   - Effort : 0.5 j
   - Doc finalisation sprint CEO 03/08+1
   - Fichiers : `docs/ROADMAP.md` (V5), `docs/audits/PLAN_QUANTIQUE_V11_PLUS_V4_20260803.md`, 2 skills catalogue

#### ZCode2 (2 phases)

5. **Phase 140 — L18 Edge Decay Sentinel** (ZCode2 C1)
   - Effort : 2-3 j | Gain : 60-120p
   - Sentinel de dégradation edge temps réel (proactif vs L11-L17)
   - Code : `core/v9/v9_edge_decay_sentinel.py` + tests
   - Branche : `feat/v9-zcode2-l18-edge-decay` (propre)

6. **Phase 141 — L19 News Shock Attenuator** (ZCode2 C2)
   - Effort : 1-2 j | Gain : 40-80p
   - Atténuateur news shock (réduit sizing pendant fenêtres volatilité news)
   - Code : `core/v9/v9_news_shock_attenuator.py` + tests
   - Branche : `feat/v9-zcode2-l19-news-shock` (propre)

### 📊 Métriques cibles V4 (sprint CEO 03/08+1)

| Métrique | Sprint 03/08 (V3) | Cible sprint 03/08+1 (V4) |
|---|---|---|
| Leviers quantiques ON | 12 | **17** |
| Tests verts | 167 | **240+** |
| Bénéfice projeté 30j | +1988-2688p | **+2600-3200p** |
| Nouveaux kill switches | 12 | **17** |
| Skills catalogue V9 | 34 | **38+** |
| Commits sprint CEO | 22 | **35+** |

### Doctrine V4

- R2 additif (NEW modules, 0 modif core/ partagé)
- R6 fail-open (kill switch OFF + données absentes → 1.0 / pass-through)
- R7 tests verts (baseline 167 préservée + ~73 nouveaux)
- R8 doc (ROADMAP V5 + PLAN V4 + 4 skills catalogue)
- R14 git vérité (SQL live, JAMAIS inventer)
- R22 sous-unité unique (1 phase = 1 module + 1 test + 1 commit)
- R25' motion CEO explicite (kill switches défauts OFF)
- R26 DECISIONS_LOG entry dédiée par livraison
- R28 multi-IA (Hermes2 orchestrateur, ZCode2 implémentation, CEO motion)

### Multi-IA V4 (R28)

| Acteur | Rôle | V4 sprint |
|---|---|---|
| **Hermes2 (M3)** | Orchestrateur git unique + H2-1 à H2-4 | 4 phases Hermes + push + merge |
| **ZCode2 (M3)** | Implémentation branche propre (Z2-1, Z2-2) | 2 phases ZCode2 + report |
| **CEO Søn** | Validateur + motion + push parallèle | si motions CEO nécessaires |

**0 conflit git** : Hermes2 = `feat/v9-foundation-clean`, ZCode2 = `feat/v9-zcode2-*`. Merge par Hermes2 seul (R28 strict).

---

_Référence : `docs/ROADMAP.md` V4 (parallélisée Hermes2 × ZCode2),
`docs/audits/PLAN_QUANTIQUE_V11_PLUS_V3_20260803.md` (V3 initial),
ce document V4 enrichi sprint CEO 03/08+1._