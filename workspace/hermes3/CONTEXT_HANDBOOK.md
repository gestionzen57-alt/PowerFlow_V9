# CONTEXT HANDBOOK — Hermes3 (session V5, parallélisé avec ZCode3)

> **Lecture obligatoire** avant de commencer un chantier Hermes3.
> Héritage de Hermes2 (sprint CEO 03/08+1 V4 finalisé) avec extensions V5.

## État du sprint CEO 03/08+1 (V4) — FINALISÉ (2026-08-03 17:50 UTC)

**HEAD actuel** : `858fc7c` (déjà pushé sur `origin/feat/v9-foundation-clean`).
**Branche locale** : `feat/v9-foundation-clean` (tu es Hermes3, push autorisé).

**Sprint V4 récap** :
- 26 commits sprint CEO total (V3 + V4)
- 14 leviers quantiques ON (L7+L8+L9+L10+L11+L12+L13+L16+L17×3+L18+V4+DD+RL)
- 192 tests verts cumulés (baseline 81 préservée + 111 nouveaux)
- Bénéfice projeté 30j : +2038-2788 pips
- Architecture parallélisée Hermes2 × ZCode2 validée

**Sprint V5 (toi)** : 5 phases à livrer, bénéfice cible +2800-3300 pips.

## Sprint CEO 03/08+2 (V5) — 5 phases Hermes3

1. **Phase 141** L19 News Shock Attenuator (à déléguer ZCode3 ou coder soi-même)
2. **Phase 142** ROADMAP V5 + PLAN V5 finalisé (0.5 j)
3. **Phase 145** Audit live mardi 04/08 (24h post-activation)
4. **Phase 146** Audit live vendredi 08/08 (semaine post-activation)
5. **Phase 147** Push final + bilan CEO V5

**Effort total Hermes3** : 4-5 jours parallelisable avec ZCode3 (3-5 j).

## Doctrine (héritage Hermes V3+V4, inchangée)

| Règle | Application Hermes3 |
|---|---|
| **R2 additif** | NEW modules uniquement, 0 modif core/ partagé. |
| **R6 fail-open** | JAMAIS d'exception non capturée. Kill switches défauts OFF. |
| **R7 tests verts** | Livrer 5-15 tests par module. Tests AVANT commit. |
| **R14 git vérité** | Audit SQL live, JAMAIS inventer de chiffres. |
| **R22 sous-unité unique** | 1 phase = 1 module + 1 test + 1 commit. |
| **R25' motion CEO** | Kill switches défauts OFF. Activation = motion CEO. |
| **R26 DECISIONS_LOG** | 1 entrée par livraison dans `workspace/perplexity/memory/DECISIONS_LOG.md`. |
| **R28 multi-IA** | Hermes3 = orchestrateur (push final). ZCode3 = branche propre (0 push). |

## Modules core/ à NE PAS MODIFIER (sauf additif)

| Module | Rôle |
|---|---|
| `core/v9/kill_switches.py` | Ajouter fonction accesseur en fin de fichier. |
| `core/v9/v9_mega_edge_filter.py` | NE PAS toucher (sauf si L19+ s'intègre, alors additif). |
| `core/v9/dynamic_risk_manager.py` | DRM APPLY. Ne pas toucher. |
| `core/v9/trade_engine.py` | Point d'entrée. Ne pas toucher. |
| `core/v9/auto_calibrator.py` | Boucle fermée writable. Ne pas toucher. |
| Modules V4 Hermes2 (V4 zones_state, DD tracker, regime live) | NE PAS toucher. |
| Modules ZCode2 (L18 edge decay sentinel) | NE PAS toucher. |

## Configuration

**Fichier env** : `config/v9_kill_switches.env` (lecture via `kill_switches.get()`).
**Ajouter un kill switch** = ajouter une ligne `V9_XXX=0` + section commentée explicative.

## Tests

| Pattern | Référence |
|---|---|
| Module L7+L8+L9+L11 (mega_edge_filter) | `tests/test_v9_mega_edge_l*.py` |
| Module L15 (heatmap) | `tests/test_v9_heatmap_l15.py` |
| Pyramiding V2/V3/V4 | `tests/test_v9_pyramiding_engine_v{2,3,4}.py` |
| L13 vol realized | `tests/test_v9_vol_realized_tp_sl.py` |
| L17 cross blacklist | `tests/test_v9_cross_blacklist.py` |
| Risk Attribution | `tests/test_v9_risk_attribution.py` |
| L12 Correlation (ZCode) | `tests/test_v9_correlation_filter.py` |
| L16 Asymmetry (ZCode) | `tests/test_v9_direction_asymmetry.py` |
| L18 Edge Decay (ZCode2) | `tests/test_v9_edge_decay_sentinel.py` |
| V4 Adaptive DD (Hermes2) | `tests/test_v9_adaptive_dd_tracker.py` |
| V4 Regime Live (Hermes2) | `tests/test_v9_regime_live_detector.py` |

## DB source

`data/v9_forces.db` (5.1 GB, 27 tables, 64 index).
Lecture OK. Écriture restreinte (voir kill_switches writables).

## Branche de travail Hermes3

```bash
cd C:/projet/V9
git checkout feat/v9-foundation-clean
git pull origin feat/v9-foundation-clean
# Travail directement sur la branche principale (tu es Hermes3, orchestrateur)
git add <fichiers_du_périmètre>
git commit -m "feat(v9): Phase 14X <description>"
git push origin feat/v9-foundation-clean  # Hermes3 = orchestrateur, push autorisé
```

## Anti-patterns (à éviter)

- ❌ Modifier un fichier core/ partagé sans respecter le pattern existant.
- ❌ Inventer des chiffres ou métriques (R14 strict).
- ❌ Commit sans tests verts (R7 strict).
- ❌ Mélanger plusieurs phases dans un même commit (R22 strict).
- ❌ Toucher aux fichiers de ZCode3 (branche feat/v9-zcode3-*) sans merger.

## Compétences à appliquer

- Audit SQL live (sqlite3 + datetime.fromisoformat)
- Composition multiplicative (Pyramiding V2 × V3 MTF × V4 zones)
- Kill switches avec défauts OFF
- Tests pytest avec monkeypatch.env + reload
- Markdown rapport (render_report, top_risk_concentrations)

## Skills catalogue V9 (référence — 38 skills)

- 25 skills pré-existants (Phase 9-12)
- `skills/powerflow-v9-heatmap-l15/SKILL.md`
- `skills/powerflow-v9-l11-dow-filter/SKILL.md`
- `skills/powerflow-v9-correlation-l12/SKILL.md`
- `skills/powerflow-v9-direction-asymmetry/SKILL.md`
- `skills/powerflow-v9-vol-realized-tpsl/SKILL.md`
- `skills/powerflow-v9-risk-attribution/SKILL.md`
- `skills/powerflow-v9-pyramiding-v3-mtf/SKILL.md`
- `skills/powerflow-v9-cross-blacklist/SKILL.md`
- `skills/powerflow-v9-edge-decay-sentinel/SKILL.md`
- `skills/powerflow-v9-pyramiding-v4-zones/SKILL.md`
- `skills/powerflow-v9-adaptive-dd-tracker/SKILL.md`
- `skills/powerflow-v9-regime-live-detector/SKILL.md`

## Patterns à suivre (look-and-feel code V9)

```python
# ── Phase XXX — Description (2026-08-04) ────────────────────────────
# Audit SQL live 04/08 (n=X) :
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

## Convergence V5

- Hermes3 + ZCode3 travaillent en parallèle
- Hermes3 merge les branches ZCode3 dans feat/v9-foundation-clean
- Hermes3 push final sur origin (R28 strict)
- Chaque livraison = 1 commit atomique + 1 entry DECISIONS_LOG

---

**Go. Tu as 4-5 jours. Sprint CEO mode « plein pouvoir » V5. R7 + R14 + R22 + R25' + R26 + R28 strict.**

Hermes3 orchestre. ZCode3 implémente. CEO Søn valide.

*Handbook préparé par Hermes le 2026-08-03 17:50 UTC pour Hermes3 (sprint CEO 03/08+2 V5).*