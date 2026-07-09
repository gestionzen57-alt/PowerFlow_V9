---
name: powerflow-v9-zone-detector
description: "ZoneDetector V9 — alimentation de zone_diagnostics, z-score, machine à états, tension, pullbacks, absorption. Gap comblé le 2026-07-06."
category: trading
tags: [v9, zone_diagnostics, z-score, state-machine, gap-completed]
statut: actif
derniere_maj: 2026-07-09
version: 0.0.1
note_chantier: aligne au HEAD b256faa (878 tests, supervision H24 LIVE)
---
# PowerFlow V9 — ZoneDetector (zone_diagnostics)

## Purpose

The `zone_diagnostics` table was created (`core/v9/zone_db.py`, 30 columns) during Phase 9 but **never populated** by any detector. This left 9 `node_rule` ACTIVE principles at 0% hit rate because their context fields (`state`, `z_current`, `bars_in_extreme`, `tension_score`, etc.) were always `None`.

`ZoneDetector` (`core/v9/zone_detector.py`) fills this gap. It computes per-currency zone diagnostics at each snapshot: z-score, zone state machine, tension score, absorbed pullbacks, and absorption factor.

## Files

- `core/v9/zone_detector.py` (412 lines) — the detector
- `core/v9/zone_db.py` — schema (pre-existing, not modified)
- `core/v9/orchestrator.py` — wired between `regime_detector` and `principle_engine`
- `scripts/regenerate_chain.py` — `zone_diagnostics` added to `DERIVED_TABLES`
- `tests/test_zone_detector.py` — 14 tests

## Architecture

### Call chain (in orchestrator.py)
```
scene_builder → behavior_analyzer → window_gate → exploitability_evaluator
→ regime_detector → **zone_detector** → principle_engine → signal_generator → decision_logger
```

Same fail-soft pattern as all other layers: each step is wrapped in `try/except`, any failure stops the chain at that step and logs the error.

### Per-currency computation (inside `detect()`)

For each of the 8 currencies, given a `forces_snapshot`:

1. **Load force history** — last 20 snapshots for same symbol+timeframe (non-stale)
2. **Compute z-score** — `(value - mean) / stdev`. Fallback if stdev=0 or n<2: `(value - 50) / 25`
3. **Determine zone state** — 5-state machine:
   - `NEUTRAL`: |z| < 1.0
   - `EARLY_EXTREME`: |z| >= 1.0, no prior extreme state
   - `ACCUMULATING`: |z| >= 1.0, same direction as previous snapshot
   - `LEAKING`: |z| >= 1.0, opposite direction from previous
   - `RUPTURE`: |z| >= 2.0
4. **Direction** — `UP` if z > 0, `DOWN` if z < 0
5. **bars_in_extreme** — count consecutive snapshots with |z| >= 1.0
6. **tension_score** — `|z| * (1 + CV)` where CV = coefficient of variation of last 3 force values. Minimum 0.5 when in extreme.
7. **absorbed_pullbacks** — count of temporary exits from extreme zone (|z| drops below 1.0 then returns)
8. **absorption_factor** — weighted combination: `tension * 0.4 + pullbacks * 0.3 + normalized_bars * 0.3`
9. **zone_level** — `|z_current|`, rounded to 4 decimals

### Persistence

- `INSERT OR REPLACE` — unique constraint on `(forces_snapshot_ref, currency)` ensures idempotence
- All 30 columns of `zone_diagnostics` are written
- Fields without runtime computation remain at defaults: `depth_slope=0.0`, `depth_acceleration=0.0`, `context_score=0.0`, `profile_name=""`, `rank_position=0`, `rank_total=0`

## Thresholds (in zone_detector.py)

| Threshold | Value | Meaning |
|---|---|---|
| `Z_SCORE_THRESHOLD_EXTREME` | 1.0 | |z| >= 1.0 = entering extreme zone |
| `Z_SCORE_THRESHOLD_RUPTURE` | 2.0 | |z| >= 2.0 = rupture |
| `TENSION_SCORE_MIN` | 0.5 | floor for tension_score in extreme |
| `PULLBACK_LOOKBACK` | 5 | snapshots to look back for pullback detection |

These are provisional — recalibrate after n>=50 live M5+ snapshots via `python scripts/v9_ops.py calibrate`.

## Principles unlocked

7 of the 9 `node_rule` ACTIVE principles became triggerable once `zone_diagnostics` was populated:

| Principle | Fields used from zone_diagnostics |
|---|---|
| `NODE_BIRTH_FAST` | state, prev_state, z_current, bars_in_extreme |
| `ZONE_RETEST` | prev_state, state, z_extreme_dir, prev_z_extreme_dir, bars_in_extreme |
| `ELASTIC_BREATH` | state, absorbed_pullbacks |
| `GRAVITY_RESPRING_NODE` | state, prev_state |
| `POWER_ANGLE_BREAK_TO_PRICE_IMPACT` | state, tension_score |
| `PRICE_LAG_AT_NODE_BIRTH` | state, tension_score |
| `RAW_NODE_BIRTH` | prev_state, state |

2 principles remain blocked (fields outside zone_diagnostics schema — handled by grammar completion, see `powerflow-v9-principle-context-enrichment`).

## Test patterns

```python
# Pattern: simulate a force series and verify zone state
def insert_bar(db_path, *, force_gbp: float, bar_time: int, **kwargs) -> str:
    # Insert a forces_snapshot row, return snapshot_id

def insert_series(db_path, forces: list[float]) -> str:
    # Insert series, return last snapshot_id

def read_zone_diagnostics(db_path, snapshot_id) -> list[dict]:
    # Read back zone_diagnostics rows for a snapshot

# Test: neutral (z near 0)
snapshot_id = insert_series(db_path, [50.0, 50.0, 50.0])
detector = ZoneDetector(db_path=db_path)
detector.detect(snapshot_id)
zone = gbp_zone(read_zone_diagnostics(db_path, snapshot_id))
assert zone["state"] == "NEUTRAL"

# Test: accumulating consecutive extremes
sid4 = insert_bar(db_path, bar_time=3, force_gbp=75.0)  # EARLY_EXTREME
ZoneDetector(db_path=db_path).detect(sid4)
sid5 = insert_bar(db_path, bar_time=4, force_gbp=78.0)  # same dir → ACCUMULATING
ZoneDetector(db_path=db_path).detect(sid5)
zone = gbp_zone(read_zone_diagnostics(db_path, sid5))
assert zone["state"] == "ACCUMULATING"
```

## Pitfalls

- ❌ `PRAGMA table_info` uses `d[0]` as index (cid), `d[1]` as column name. **Always use `d[1]`** for column names.
- ❌ `abs_z` must be defined **inside the absorption_factor block**, not inherited from a removed placeholder section.
- ❌ `depth_slope` and `depth_acceleration` must remain defined even after replacing the `absorption_factor` placeholder — removing them while they're still referenced in the INSERT causes `NameError`.
- ❌ The `zone_detector.py` docstring still mentions "2 principes ACTIVE restent bloqués" — this was true before grammar completion (commit `a596f37`). After grammar completion, all 9 `node_rule` ACTIVE are triggerable. Update the docstring if modified.
- ❌ Confusing "zone_diagnostics populated" with "grammar complete" — zone_diagnostics alone unblocked 7/9 principles. The remaining 2 (ANTAGONIST_NODE, COALITION_NODE) were unblocked by enriching `_load_shared_context()` with coalition_strength and cross-TF fields, not by zone_diagnostics itself.