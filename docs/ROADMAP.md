# ROADMAP V3 — PowerFlow V9 (2026-08-03 06:30+ UTC)

> **Mode CEO no-stop 03/08** : « optimisation max, plein pouvoir, pas
> d'arrêt ». Sprint parallélisé Hermes (orchestrateur git unique) + ZCode
> (implémentation assistée, chantier git-indépendant).
>
> **Convergence** : HEAD `b4d6c3b` (pushé origin), 13 commits sprint CEO,
> 9 leviers L7-L11 ON, 103 tests verts (0 fails).

## Sprint 03/08 — récap CEO no-stop

| Phase | Levier | Statut | Commit |
|---|---|---|---|
| 105 | OOS freeze test STABLE | ✅ | `eb3ef75` |
| 12/03/08 | PyramidingEngine V2 STARS/SUPER_STARS | ✅ | `603fce7` |
| 03/08 | Activation 7 kill switches CEO | ✅ | `45a4dd6` |
| 03/08 | Auto-calibrator premier run | ✅ | `d5f6692` |
| 03/08 | DECISIONS_LOG sprint entry | ✅ | `7ccdc41` |
| 03/08 | Audit CVaR + proposition recalibrage | ✅ | `4798467` |
| 03/08 | Audit A16 walk-forward L7/L8/L9 | ✅ | `19179bc` |
| 126 | **L15 heatmap regime × session × pattern** | ✅ | `c632698` |
| 127 | **L11 GBPUSD × Mer boost + Mar blacklist** | ✅ | `26cd0c6` |
| 03/08 | Docs piliers + skills + MCP | ✅ | `c0f2f5d` |
| 03/08 | A1 tokens Telegram (CEO en parallèle) | ✅ | `a5e1b22` |

**Bénéfice mesuré** : +758.5 pips L7+L8 walk-forward.
**Bénéfice projeté** : +1278.5 pips L7+L8+L9, +300-600 pips L11+L15 = **+1578-1878 pips**.

---

## ROADMAP V3 — 5 phases parallélisées (Hermes × ZCode)

### Architecture de parallélisation

```
┌──────────────────────────────────────────────────────────────────────┐
│                          HERMES (orchestrateur)                      │
│  - Lit AGENTS.md + STATE.md                                          │
│  - Agrège commits ZCode                                              │
│  - Push final origin/feat/v9-foundation-clean                        │
│  - DECISIONS_LOG entry dédiée par phase                              │
│  - 1 sprint = 1 périmètre = 1 livraison (R22)                        │
└──────────────────────────────────────────────────────────────────────┘
            │                                      │
            │ (chantier A)                         │ (chantier B)
            ▼                                      ▼
┌──────────────────────────┐         ┌────────────────────────────────┐
│  HERMES_SESSION (moi)    │         │  ZCODE_SESSION (parallèle)    │
│  Phase 128/129/130       │         │  Phase 128 L12 OR 129 L16      │
│  - L12 corrélation       │         │  - Branche feat/v9-zcode-XXX   │
│  - Patch SOUL/AGENT      │         │  - 0 modif core/ partagé       │
│  - Push si seul          │         │  - Commit sur branche propre  │
│  - Merge orchestrateur   │         │  - PR-like report à Hermes     │
└──────────────────────────┘         └────────────────────────────────┘
```

### Chantiers git-indépendants (pas de conflit)

| Chantier | Owner | Fichiers touchés | Effort | Branche |
|---|---|---|---|---|
| **C1 — Phase 128 L12 corrélation × régime** | ZCode | `core/v9/v9_correlation_filter.py` (NEW), `core/v9/kill_switches.py` (ajout), `config/v9_kill_switches.env`, `tests/test_v9_correlation_filter.py` | 2-3 j | `feat/v9-zcode-l12-correlation` |
| **C2 — Phase 129 L16 asymétrie WR par direction** | ZCode | `core/v9/v9_direction_asymmetry.py` (NEW), `core/v9/kill_switches.py` (ajout), `config/v9_kill_switches.env`, `tests/test_v9_direction_asymmetry.py` | 2-3 j | `feat/v9-zcode-l16-asymmetry` |
| **C3 — Phase 130 L13 adaptive TP/SL vol realized** | Hermes (après C1/C2) | `core/v9/dynamic_tp_sl.py`, `core/v9/v9_vol_realized_filter.py` (NEW), tests | 3-5 j | `feat/v9-foundation-clean` |
| **C4 — Patch ROADMAP_V3 + PLAN_QUANTIQUE_V3** | Hermes | `docs/ROADMAP.md`, `docs/audits/PLAN_QUANTIQUE_V11_PLUS_20260803.md` (V11+ V3) | 0.5 j | `feat/v9-foundation-clean` |
| **C5 — Skills catalogue V3 (L12/L13/L16)** | Hermes | `skills/powerflow-v9-correlation-filter/`, `skills/powerflow-v9-direction-asymmetry/`, `skills/powerflow-v9-vol-realized-tpsl/` | 1 j | `feat/v9-foundation-clean` |

### Sprint immédiat (Phase 128-129 — ZCode)

**ZCode prompt** (chantier C1 OU C2, au choix — voir prompts dédiés plus bas) :
- Crée sa branche depuis `b4d6c3b` (HEAD actuel, déjà pushé).
- Travaille **uniquement** sur les fichiers de son périmètre (voir prompts).
- Commit atomique par livraison (R26).
- **NE TOUCHE PAS** aux fichiers hors périmètre.
- **NE PUSH PAS** sur origin (R28 : Hermes seul).
- Reporte à Hermes : (1) branche créée, (2) commits atomiques, (3) tests verts,
  (4) diff résumée.

### Convergence sprint CEO 03/08+1

1. **ZCode démarre C1 OU C2** (au choix, prompt copy-paste ready).
2. **Hermes patche ROADMAP V3 + PLAN V11+ V3 + skills C5** en parallèle.
3. **Hermes agrège** : merge des branches ZCode → `feat/v9-foundation-clean`.
4. **DECISIONS_LOG entry dédiée** par phase livrée.
5. **Push final** unique (R28 strict).

### Métriques de succès

| Métrique | Actuel (03/08 06:30) | Cible V3 (08/08) |
|---|---|---|
| Leviers quantiques ON | 9 | 14-15 (L12+L13+L16 = +3-6) |
| Tests verts | 103 | 200+ |
| Bénéfice projeté | +1278.5p L7+L8+L9 | +2200p (+ L12+L13+L16) |
| Nouveaux kill switches | 9 ON | 14-15 ON |
| Skills catalogue V9 | 28 | 32 (+ L12+L13+L16 + L15+L11) |

### Doctrine

- R7 tests verts obligatoires par livraison.
- R14 git vérité (chiffres du SQL réel, pas inventés).
- R22 sous-unité unique par phase.
- R25' motion CEO explicite pour activation kill switch.
- R26 1 commit + 1 DECISIONS_LOG entry par livraison.
- R28 Hermes opérateur git unique (push + merge).
- Multi-IA : ZCode (implémentation, branche propre, 0 push), Hermes
  (orchestrateur, push + merge + report).

---

## Prompts ZCode copy-paste ready

Voir fichiers dédiés :
- `workspace/zcode/PROMPT_PHASE128_L12_CORRELATION.md`
- `workspace/zcode/PROMPT_PHASE129_L16_ASYMMETRY.md`
- `workspace/zcode/CONTEXT_HANDBOOK.md` (contexte minimal obligatoire)