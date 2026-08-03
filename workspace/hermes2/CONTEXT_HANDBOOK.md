# CONTEXT HANDBOOK — Hermes2 (session +1, parallélisé avec ZCode2)

> **Lecture obligatoire** avant de commencer un chantier Hermes2.
> Héritage de Hermes (sprint CEO 03/08 V3) avec extensions V4.

## État du sprint CEO 03/08 finalisé (2026-08-03 07:30 UTC)

**HEAD actuel** : `83677a2` (déjà pushé sur `origin/feat/v9-foundation-clean`).
**Branche locale** : `feat/v9-foundation-clean`.

**ZCode a livré ses 2 prompts** :
- Phase 128 L12 Correlation (commit `7ed5c55`, branche feat/v9-zcode-l12-correlation mergée)
- Phase 129 L16 Asymmetry (commit `83677a2`, branche feat/v9-zcode-l16-asymmetry mergée)

**Commandes utiles** :
```bash
cd C:/projet/V9
git log --oneline -10
git status --short
```

**Tests baseline** : `cd C:/projet/V9 && .venv/Scripts/python -m pytest tests/ -q --tb=short`
**Tests sprint CEO 03/08** : 167 verts cumulés (cf. PLAN V11+ V4).

## Sprint CEO 03/08+1 (V4) — 4 phases Hermes2

1. **Phase 136 — Pyramid Engine V4 (zones_state boost)** : 2-3 j
2. **Phase 137 — Adaptive Drawdown Tracker** : 2 j
3. **Phase 138 — Regime Live Detector (DOW × regime × vol)** : 1-2 j
4. **Phase 139 — ROADMAP V5 + PLAN V4 + Skills catalogue V4** : 0.5 j

**Effort total Hermes2** : 6-8 j parallelisable avec ZCode2 (2-5 j).

## Doctrine (inchangée depuis sprint CEO 03/08 V3)

| Règle | Application Hermes2 |
|---|---|
| **R2 additif** | NEW modules uniquement, 0 modif core/ partagé. |
| **R6 fail-open** | JAMAIS d'exception non capturée. Kill switches défauts OFF. |
| **R7 tests verts** | Livrer 5-15 tests par module. Tests AVANT commit. |
| **R14 git vérité** | Audit SQL live, JAMAIS inventer de chiffres. |
| **R22 sous-unité unique** | 1 phase = 1 module + 1 test + 1 commit. |
| **R25' motion CEO** | Kill switches défauts OFF. Activation = motion CEO. |
| **R26 DECISIONS_LOG** | 1 entrée par livraison dans `workspace/perplexity/memory/DECISIONS_LOG.md`. |
| **R28 multi-IA** | Hermes2 = orchestrateur (push final). ZCode2 = branche propre (0 push). |

## Modules core/ à connaître (NE PAS MODIFIER sauf additif)

| Module | Rôle |
|---|---|
| `core/v9/kill_switches.py` | Chargeur central kill switches. Ajouter accesseur en fin de fichier. |
| `core/v9/v9_mega_edge_filter.py` | Filtre L1-L11. Hermes2 peut étendre avec L18+ (additif). |
| `core/v9/dynamic_risk_manager.py` | DRM APPLY. Ne pas toucher. |
| `core/v9/trade_engine.py` | Point d'entrée. Ne pas toucher. |
| `core/v9/auto_calibrator.py` | Boucle fermée writable. Ne pas toucher. |
| `core/v9/v9_pyramiding_engine_v3.py` | V3 MTF boost (Phase 133). V4 doit hériter (R2). |
| `core/v9/v9_cross_blacklist.py` | L17 cross blacklist (Phase 134). Référence. |
| `core/v9/v9_risk_attribution.py` | Phase 132. Référence pour analytics. |

## Configuration

**Fichier env** : `config/v9_kill_switches.env` (lecture via `kill_switches.get()`).
**Ajouter un kill switch** = ajouter une ligne `V9_XXX=0` + section commentée explicative.

## Tests

| Pattern | Référence |
|---|---|
| Module L7+L8+L9+L11 (mega_edge_filter) | `tests/test_v9_mega_edge_l*.py` |
| Module L15 (heatmap) | `tests/test_v9_heatmap_l15.py` |
| Pyramiding V2 | `tests/test_v9_pyramiding_engine_v2.py` |
| Pyramiding V3 (MTF) | `tests/test_v9_pyramiding_engine_v3.py` |
| L13 vol realized | `tests/test_v9_vol_realized_tp_sl.py` |
| L17 cross blacklist | `tests/test_v9_cross_blacklist.py` |
| Risk Attribution | `tests/test_v9_risk_attribution.py` |
| L12 Correlation (ZCode) | `tests/test_v9_correlation_filter.py` |
| L16 Asymmetry (ZCode) | `tests/test_v9_direction_asymmetry.py` |

## DB source

`data/v9_forces.db` (5.1 GB, 27 tables, 64 index).
Lecture OK. Écriture restreinte (voir kill_switches writables).

## Branche de travail Hermes2

```bash
cd C:/projet/V9
git checkout feat/v9-foundation-clean
# Travail directement sur la branche principale (tu es Hermes2, orchestrateur)
git add <fichiers_du_périmètre>
git commit -m "feat(v9): Phase 13X <description>"
git push origin feat/v9-foundation-clean  # Hermes2 = orchestrateur, push autorisé
```

## Anti-patterns (à éviter)

- ❌ Modifier un fichier core/ partagé sans respecter le pattern existant.
- ❌ Inventer des chiffres ou métriques (R14 strict).
- ❌ Commit sans tests verts (R7 strict).
- ❌ Mélanger plusieurs phases dans un même commit (R22 strict).
- ❌ Toucher aux fichiers de ZCode2 (branche feat/v9-zcode2-*) sans merger.

## Compétences à appliquer

- Audit SQL live (sqlite3 + datetime.fromisoformat)
- Composition multiplicative (Pyramiding V2 × V3 MTF × V4 zones)
- Kill switches avec défauts OFF
- Tests pytest avec monkeypatch.env + reload
- Markdown rapport (render_report, top_risk_concentrations)

## Skills catalogue V9 (référence)

- `skills/powerflow-v9-heatmap-l15/SKILL.md`
- `skills/powerflow-v9-l11-dow-filter/SKILL.md`
- `skills/powerflow-v9-correlation-l12/SKILL.md`
- `skills/powerflow-v9-direction-asymmetry/SKILL.md`
- `skills/powerflow-v9-vol-realized-tpsl/SKILL.md`
- `skills/powerflow-v9-risk-attribution/SKILL.md`
- `skills/powerflow-v9-pyramiding-v3-mtf/SKILL.md`
- `skills/powerflow-v9-cross-blacklist/SKILL.md`

## Patterns à suivre (look-and-feel code V9)

```python
# ── Phase XXX — Description (2026-08-03) ────────────────────────────
# Audit SQL live 03/08 (n=337) :
#   Cas A : n=X WR=Y% PNL=Z (description)
#   Cas B : n=X WR=Y% PNL=Z (description)
# Gain projete : X pips. Cout : Y%.
# Additif (R2), defaut OFF (R25' strict motion CEO), R6 fail-open.
def new_module_accesseur() -> bool:
    """Kill switch V9_XXX_ENABLED — Phase XXX (date).

    Description courte (1 phrase du role).
    Defaut OFF (R25' strict motion CEO).
    Additif (R2), R6 jamais bloquant.
    """
    return get("V9_XXX_ENABLED", "0") == "1"
```

## Convergence V4

- Hermes2 + ZCode2 travaillent en parallèle
- Hermes2 merge les branches ZCode2 dans feat/v9-foundation-clean
- Hermes2 push final sur origin (R28 strict)
- Chaque livraison = 1 commit atomique + 1 entry DECISIONS_LOG

---

**Go. Tu as 6-8 jours. Sprint CEO mode « plein pouvoir » V4. R7 + R14 + R22 + R25' + R26 + R28 strict.**

Hermes2 orchestre. ZCode2 implémente. CEO Søn valide.