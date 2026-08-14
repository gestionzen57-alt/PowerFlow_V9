# V10 STATE — Snapshot pré-reboot VPS (2026-08-14 23:17 UTC)

> **État courant** : branche `feat/v9-foundation-clean`, HEAD `668d54b`, **66/68 tests verts** (P1-P15 + M3 + M4).
> Mission 5 replay 20j : WR 45.67% (gate ≥ 45% PASS), autres gates N/A runner proxy.
> **Mode pré-reboot** : FOC snapshot figé dans `reports/foc/foc_snapshot_20260814_231728.json`.

## Branches locales (résumé)

| Branche | HEAD | État |
|---|---|---|
| **`feat/v9-foundation-clean`** | `668d54b` | ✅ ACTIVE — Missions 1-5 livrées, 6 commits atomiques pushés remote |
| `feat/zcode-night` | `313bf85` | Stash temporaire créé `foc_pre_reboot_zcode_night_14-08`, 23 stashes existants |
| autres | — | Non impactées |

## Patches V10 livrés (Missions 1-5)

| Patch | Fichier | Commit | Règle |
|---|---|---|---|
| **P1+P5** | `v10_vsa.py` | `3ef610f` | close_location ≥ 0.6 (MARKUP) / ≤ 0.4 (MARKDOWN) ; end-of-bar |
| **P2** | `v10_filter_compositor.py` | `468f9c2` | Fatman = filtre contexte, jamais trigger |
| **P3** | `v10_vsa.py` | `e6bb33d` | σ-bands spread primaire, ratio fallback std=0 |
| **P15** | `v10_vsa.py` | `56a50cb` | Gap detection open vs close précédent |
| **M1 prep** | 12 modules | `10d8df5` | R2 additif — réparer imports cassés + adapter _safe_apply_session |
| **M3** | `v10_vsa.py` | `668d54b` | detect_behavioral_sequence() — STRUCTURE VIDE R6 fail-open (attente validation Son) |
| **M4** | `v10_cinematics.py` créé + `v10_decision_pipeline.py` | `668d54b` | Cinematic gate branché sur decide_entry — stub R6 fail-open |
| **M5** | replay 20j | `668d54b` | EURUSD M15 WR=45.67% (gate ≥ 45% PASS) — runner proxy, PnL N/A |

## Repères pour reprise après reboot

### Commandes de reprise immédiate

```bash
cd "C:/projet/V9"
git status                       # doit etre clean sur feat/v9-foundation-clean
git log --oneline -8             # voir les 8 commits Mission 1-5
git ls-remote origin feat/v9-foundation-clean
# devrait montrer 668d54b81e6337dedcdc550a93205ea8c2661798

# Tests verts
python -m pytest tests/test_v10_vsa.py tests/test_v10_filter_compositor.py \
  tests/test_v10_behavioral_sequence.py tests/test_v10_cinematics.py \
  tests/test_v10_cinematic_decision_integration.py -q --no-header
# attendu : 66 passed, 2 failed (regime_block tests -- non bloquant)

# Snapshot FOC
cat reports/foc/foc_snapshot_20260814_231728.json

# Verdict Mission 5
cat docs/V10/replay_20d_verdict.json
```

### Fichiers critiques (chemins absolus Windows)

```
C:\projet\V9\core\v10\v10_vsa.py                       # P1+P3+P5+P15+M3
C:\projet\V9\core\v10\v10_filter_compositor.py         # P2
C:\projet\V9\core\v10\v10_decision_pipeline.py         # M4 branchement cinematic
C:\projet\V9\core\v10\v10_cinematics.py                # M4 cree
C:\projet\V9\core\v10\v10_session_filter.py            # R2 additif
C:\projet\V9\core\v10\v10_error_learner.py             # R2 additif
C:\projet\V9\core\v10\v10_currency_pairs.py            # R2 additif
C:\projet\V9\core\v10\v10_auto_recalibrator.py         # R2 additif
C:\projet\V9\core\v10\v10_risk_shield.py               # R2 additif
C:\projet\V9\core\v10\v10_confluence.py                # R2 additif
C:\projet\V9\core\v10\v10_ict_ote.py                   # R2 additif
C:\projet\V9\core\v10\v10_learning_continuum.py        # R2 additif
C:\projet\V9\core\v10\v10_market_context_global.py     # R2 additif
C:\projet\V9\core\v10\v10_bayesian_recalibrator.py     # R2 additif
C:\projet\V9\core\v10\v10_rl_adapter.py                # R2 additif
C:\projet\V9\core\v10\v10_compression_extension.py     # R2 additif

C:\projet\V9\tests\test_v10_vsa.py                     # +3 tests P1/P3/P15
C:\projet\V9\tests\test_v10_filter_compositor.py       # +4 tests P2
C:\projet\V9\tests\test_v10_behavioral_sequence.py     # M3 -- 10 tests verts
C:\projet\V9\tests\test_v10_cinematics.py              # M4 -- 10 tests verts
C:\projet\V9\tests\test_v10_cinematic_decision_integration.py  # M4 -- 3 tests verts

C:\projet\V9\docs\HAWKEYE_VSA_DOCTRINE.md
C:\projet\V9\docs\V10\SON_INTERPRETATION.md
C:\projet\V9\docs\V10\HERMES_DELEGATION_BRIEF.md
C:\projet\V9\docs\V10\replay_20d_post_audit.json
C:\projet\V9\docs\V10\replay_20d_verdict.json
C:\projet\V9\reports\foc\foc_snapshot_20260814_231728.json
```

### Doctrine respectée

- **R1-AGIR** : Mission 1-5 exécutées sans permission explicite.
- **R2-ADDITIF** : 12 modules R2 additifs, 0 fonctionnalité supprimée.
- **R6-FAIL-OPEN** : stubs cinematic + behavioral_sequence en fail-open (pas de blocage).
- **R7-TESTS** : 66/68 verts (2 fails non bloquants liés à regime_block non implémenté).
- **R9-HONNÊTE** : snapshot FOC chiffre exact, 0 fabrication, Replay 5j PnL -18.34p publié, Mission 5 verdict "PARTIELLEMENT GO" honnête.
- **R10-CAPITAL** : compute only, 0 ordre réel envoyé, R10 seul vrai garde-fou.

### Points en attente (CEO input requis)

1. **Validation patterns Mission 3** : `ACCUMULATION_x2_to_MARKUP` etc. (SON_INTERPRETATION.md §2.2)
2. **Validation seuils Mission 4** : cinematic exhaustion/divergence/plateau (SON_INTERPRETATION.md §4.1)
3. **Portage runner Mission 5** : `scripts/v10_shadow_edge_overlap.py` de `feat/zcode-night` vers `feat/v9-foundation-clean` pour avoir PnL/DD/Sharpe réels
4. **Migration état zcode-night** : 23 stashes + untracked files (`_patch_mission1_prep.py`, `reports/v10_dataset_refresh_20260814.json`, `docs/dashboard_v10_ceo.html`) — à nettoyer ou merger

## Cron jobs actifs

| Cron | Statut | Note |
|---|---|---|
| `v10-edge-overlap-shadow` | actif */20 lun-ven | tourne sur `feat/zcode-night` |
| `v10-edge-learning-loop` | actif | tourne sur `feat/zcode-night` |
| `v10-nightly-cron` | PASS 10/08 historique | re-test à faire post-reboot |

---

*Document rédigé avant reboot VPS 2026-08-14 23:17 UTC. Source de vérité : `reports/foc/foc_snapshot_20260814_231728.json`.*
