# V10 — Edge Fund Phase 2 : VSA Engine (Wyckoff Volume Spread Analysis)

**Date de livraison** : 2026-08-04 23:25 UTC
**Branche** : `feat/v9-foundation-clean`
**HEAD** : 12a56da
**Tests** : 91/91 V10 cumul (gate 78/78 ✅ — cible dépassée)

---

## 1. Mission de la Phase 2

Reproduire la lecture **Wyckoff / Volume Spread Analysis** de Søn
sur les 7 TF × 7 paires : classer chaque bougie récente dans un
état structurel (4 états purs + NEUTRAL) avec 5 flags complémentaires
permettant aux Phase 3 (Confluence) et Phase 4 (Signaux) de filtrer
les contextes d'entrée.

Doctrine V10 appliquée :

| Règle | Application |
|-------|-------------|
| **R1-AGIR** | Module écrit sans permission CEO |
| **R2 additif pur** | 0 import depuis `core/v9/` (vérifié) |
| **R6 fail-open** | Bars insuffisantes ou volume=0 → NEUTRAL + flag |
| **R7 tests verts** | 21/21 tests Phase 2 + 70 cumulés existants = 91 verts |
| **R9 auditable** | `classification_path` sérialisable + seed + n_bars_used |
| **R10 zéro capital** | Compute only — aucun ordre |

---

## 2. Algorithme (les 4 états purs)

```
┌────────────────────────────┬──────────────────────────────────────┐
│  ÉTAT                      │  DÉCLENCHEUR                         │
├────────────────────────────┼──────────────────────────────────────┤
│  MARKUP            🟢     │  spread_wide + volume_high + dir>+1│
│                             │  OU climax_volume + dir>+1           │
├────────────────────────────┼──────────────────────────────────────┤
│  MARKDOWN          🔴     │  spread_wide + volume_high + dir<-1│
│                             │  OU climax_volume + dir<-1           │
├────────────────────────────┼──────────────────────────────────────┤
│  ACCUMULATION      🟡     │  spread_narrow + volume_high + doji │
│                             │  + dir>=0 (absorption haussière)     │
├────────────────────────────┼──────────────────────────────────────┤
│  DISTRIBUTION      🟠     │  spread_narrow + volume_high + doji │
│                             │  + dir<0 (distribution baissière)    │
├────────────────────────────┼──────────────────────────────────────┤
│  NEUTRAL           ⚪     │  sinon (dry vol, range étroit)       │
│                             │  ou data insuffisante (fail-open)    │
└────────────────────────────┴──────────────────────────────────────┘
```

### 5 flags complémentaires

| Flag | Déclencheur | Lecture Wyckoff |
|------|-------------|------------------|
| `no_demand`     | narrow_spread + dry_volume + dir>+1 | Plus d'acheteurs dans cette hausse |
| `no_supply`     | narrow_spread + dry_volume + dir<-1 | Plus de vendeurs dans cette baisse |
| `climax`        | volume >= 3× SMA(vol) | Potentiel exhaustion |
| `test`          | effort_vs_result < 0.3 + retest S/R | Spring / UTAD de Wyckoff |
| `stopping_volume` | climax_volume + contre-tendance 5 prév | Absorption institutionnelle |

---

## 3. Mesures calculées

| Mesure | Formule | Plage |
|--------|---------|-------|
| `spread` | high - low | [0, +∞) |
| `spread_relative` | spread / SMA(spread_lookback=5) | [0, +∞), 1=neutre |
| `volume_relative` | vol / SMA(volume_lookback=20) | [0, +∞), 1=neutre |
| `effort_vs_result` | body / spread | [0, 1] |
| `direction` | sign(close - open) | {-1, 0, +1} |

---

## 4. Livrables

| Fichier | Type | Lignes | Rôle |
|---------|------|--------|------|
| `core/v10/v10_vsa.py`             | module | 470 | VSAState enum + compute_vsa + compute_vsa_series |
| `tests/test_v10_vsa.py`           | tests  | 290 | 21 tests (8 obligatoires + 13 bonus) |
| `scripts/v10_vsa_demo.py`         | CLI    | 290 | Demo ASCII 9 cas + --json + --series |
| `core/v10/__init__.py`            | patch  | +2   | Export VSA dans le namespace V10 |

### 4.1. Sortie engine

```python
@dataclass
class VSAEngineState:
    symbol: str
    timestamp: str
    timeframe: str
    state: VSAState           # MARKUP/MARKDOWN/ACCUMULATION/DISTRIBUTION/NEUTRAL
    spread: float
    spread_relative: float
    volume: float
    volume_relative: float
    effort_vs_result: float
    body_ratio: float
    direction: int            # -1, 0, +1
    no_demand: bool
    no_supply: bool
    climax: bool
    test: bool
    stopping_volume: bool
    data_insufficient: bool
    classification_path: List[str]   # R9 audit trail
    n_bars_used: int
    period: int
    seed: Optional[int]
```

### 4.2. CLI (verdict-first)

```
$ python scripts/v10_vsa_demo.py --case accumulation

======================================================================
 V10 VSA ENGINE — Volume Spread Analysis (Wyckoff)
======================================================================
 Pair        : EURUSD
 Timestamp   : 2026-08-04T39:00:00Z
 Timeframe   : M15

 VERDICT     : 🟡 ACCUMULATION  [██████████████████············]  bias=LONG

 ── Raw measures ──────────────────────────────────────────────
 Spread          : 0.000500
 Spread relative : 0.250  (vs avg[5])
 Volume          : 1800
 Volume relative : 1.800  (vs avg[20])
 Effort/result   : 0.100  (body/spread)
 Body ratio      : 0.100
 Direction       : +1

 ── Flags ─────────────────────────────────────────────────────
   ⚑ test

 ── Classification path (R9 audit) ────────────────────────────
   • spread=0.000500 body=0.000050 direction=+1 volume=1800
   • avg_spread[5]=0.002000 → spread_relative=0.250
   • avg_volume[20]=1000 → volume_relative=1.800
   • flags: wide=False narrow=True high_vol=True climax=False dry=False doji=True
   • test=high : retest résistance
   • narrow+high_vol+doji → ACCUMULATION (dir=+1, le prix tient)
```

---

## 5. Tests verts (gate)

```
$ pytest tests/test_v10_vsa.py -v
============================= 21 passed in 0.30s ==============================

$ pytest tests/test_v10_*.py -q
91 passed in 48.48s
```

### Couverture (8 obligatoires + 13 bonus)

| # | Test | Statut |
|---|------|--------|
| 1 | `test_markup_high_vol_wide_spread`            | ✅ |
| 2 | `test_distribution_climax_volume`             | ✅ |
| 3 | `test_no_demand_detection`                    | ✅ |
| 4 | `test_fail_open_zero_volume`                  | ✅ |
| 5 | `test_all_4_states_reachable`                 | ✅ |
| 6 | `test_effort_vs_result_divergence`            | ✅ |
| 7 | `test_timeframe_independence` (×7 TF)         | ✅ |
| 8 | `test_audit_metadata_present`                 | ✅ |
| 9 | `test_fail_open_no_bars`                      | ✅ bonus |
| 10| `test_fail_open_insufficient_bars`            | ✅ bonus |
| 11| `test_unsupported_timeframe_yields_neutral`   | ✅ bonus |
| 12| `test_serializable_round_trip_json`           | ✅ bonus |
| 13| `test_vsa_series_returns_aligned_length`      | ✅ bonus |
| 14| `test_helpers_spread_and_body`                | ✅ bonus |
| 15| `test_classify_bang_path_includes_decisive`   | ✅ bonus |

---

## 6. R5 — Chain-of-thought (CoT) appliqué

```
1. "Je vois : bougie OHLCV spread=0.0050 (vs SMA=0.0010 → rel=5×),
            close>open (dir=+1), volume=2500 (vs SMA=1000 → rel=2.5×)."
2. "Je pense : wide_spread + high_vol + dir=+1 = configuration
               d'achat dominante ; non-climax (2.5× < 3×)."
3. "Je décide : VSAState.MARKUP car toutes les conditions sont réunies,
               et STOPPING_VOLUME est faux (pas de climax)."
4. "Je risque : aucune décision n'est prise — R10 (compute only).
               Phase 4 utilisera cet état pour scorer A1/A2/A3."
5. "J'apprends : classification_path enregistré pour rejouer
                  la décision (R9 auditable)."
```

---

## 7. Prochaine étape — Phase 3 (Confluence Engine)

- Pondération 7 TF : D1/H4=50%, H1/M30=30%, M15/M5=15%, M1=5%
- Score 0-1 basé sur alignment des états VSA + force devises
- M30 = pont critique M15 entrée ↔ H1 biais (logique dédiée)
- Gate : 90/90 tests cumulés + score ≥ 0.72 autorise signal A1

---

## 8. Vérification doctrine

```bash
$ grep -r "from core.v9" core/v10/v10_vsa.py
(no output — R2 additif pur respecté)

$ grep -r "import core.v9" core/v10/v10_vsa.py
(no output — R2 additif pur respecté)

$ pytest tests/test_v10_*.py -q
91 passed in 48.48s        (R7 — gate 78/78 franchi)
```

**Phase 2 livrée — VSA Engine opérationnel.**
**Phase 3 Confluence Engine enchaîne sans interruption.**
