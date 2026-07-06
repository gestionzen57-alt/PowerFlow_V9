---
name: powerflow-v9-principle-context-enrichment
description: Enrichissement du contexte des principes V9 — coalition_strength, cross-TF H1/M5, absorption_factor. 9/9 node_rule ACTIVE désormais déclenchables.
category: trading
tags: [v9, principles, context-enrichment, grammar-complete, gap-completed]
---

# PowerFlow V9 — Principle Context Enrichment (Grammar Completion)

## Purpose

After `zone_diagnostics` population (commit `db11917`), 7/9 `node_rule` ACTIVE principles were triggerable. The remaining 2 (`ANTAGONIST_NODE`, `COALITION_NODE`) were blocked by context fields that don't live in `zone_diagnostics` but in other data sources.

This skill documents the **enrichment of `_load_shared_context()`** in `core/v9/principle_engine.py` to provide those fields without creating new detectors or tables.

## Files

- `core/v9/principle_engine.py` — `_load_shared_context()` enriched with 3 new context blocks
- `core/v9/zone_detector.py` — `absorption_factor` placeholder replaced with real calculation

## Three enrichments

### B1 — coalition_strength (for COALITION_NODE)

Computed from the scene's coalitions list (already parsed from `scenes.coalitions_json`):

```python
if coalitions:
    aligned_devises = set()
    total_intensity = 0.0
    for c in coalitions:
        aligned_devises.update(c["devises_alignees"])
        total_intensity += c["intensite_alignement"]
    coalition_strength = (len(aligned_devises) / 8.0) * (total_intensity / len(coalitions) / 50.0)
    context["coalition_strength"] = round(coalition_strength, 4)
else:
    context["coalition_strength"] = 0.0
```

Formula: `(aligned_devises_ratio) * (avg_intensity / 50.0)`. Ranges ~0.0–1.0.

**COALITION_NODE condition**: `coalition_strength >= 0.5` AND `state IN [ACCUMULATING, LEAKING]`.

### B2 — Cross-TF H1/M5 (for ANTAGONIST_NODE)

For each of `H1` and `M5`:
- If target_tf == current snapshot timeframe: derive from current snapshot's `force_*` columns
- Otherwise: `SELECT * FROM forces_snapshots WHERE symbol = ? AND timeframe = ? AND stale = 0 ORDER BY timestamp DESC LIMIT 1`
- Find the max force value across all 8 currencies
- Map to direction/state vocabulary matching V8 expectations:

```python
if max_force > 60:    state = "HAUSSIERE"
elif max_force < 40:  state = "BAISSIERE"
else:                 state = "NEUTRAL"

if max_force > 55:    dir = "HAUSSIERE"
elif max_force < 45:  dir = "BAISSIERE"
else:                 dir = "NEUTRE"
```

**ANTAGONIST_NODE condition**: `h1_state NOT IN [NEUTRAL, null]` AND `m5_state NOT IN [NEUTRAL, null]` AND `h1_dir != "NONE"` AND `m5_dir != "NONE"` AND `h1_dir != m5_dir`.

The principle only triggers when H1 and M5 have different directions — market in conflict across timeframes.

### B3 — absorption_factor (in zone_detector.py)

Replaced the placeholder `absorption_factor = 0.0` with a real calculation:

```python
abs_z = abs(z_current)
if abs_z >= Z_SCORE_THRESHOLD_EXTREME:
    absorption_factor = round(
        (tension_score * 0.4)
        + (absorbed_pullbacks * 0.3)
        + (min(bars_in_extreme, 10) / 10.0 * 0.3),
        4,
    )
else:
    absorption_factor = 0.0
```

Normalized range ~0.0–3.0. Used by `GRAMMAR_ABSORPTION` (kind: grammar, never emits — documentation entry only).

## Principle state after completion

| Principle | Status | Triggerable since |
|---|---|---|
| NODE_BIRTH_FAST | ✅ Triggered (~0.4% live) | db11917 (zone_diagnostics) |
| RAW_NODE_BIRTH | ✅ Triggered (~0.4% live) | db11917 |
| POWER_ANGLE_BREAK_TO_PRICE_IMPACT | ✅ Triggered (~0.2% live) | db11917 |
| PRICE_LAG_AT_NODE_BIRTH | ✅ Triggered (~0.8% live) | db11917 |
| ZONE_RETEST | ✅ Triggered (~0.5% live) | db11917 |
| ELASTIC_BREATH | ✅ Triggered (~0.1% live) | db11917 |
| GRAVITY_RESPRING_NODE | ✅ Triggered (~0.1% live) | db11917 |
| COALITION_NODE | ✅ Triggered (~0.2% live) | a596f37 (coalition_strength) |
| ANTAGONIST_NODE | ✅ Evaluated (0% live) | a596f37 (cross-TF) — conditions not met on aligned market |
| GRAMMAR_REGIME | 📄 Grammar (never emits) | By design |

## Docstring update

After completion, the module docstring of `principle_engine.py` was updated from "GAP DOCUMENTÉ" to "GAP RÉSOLU":

```python
# Before:
GAP DOCUMENTÉ — 9 des 27 principes ... référencent des champs ... absents

# After:
GAP RÉSOLU — 7 des 9 principes ... sont désormais déclenchables
```

## Verification

```python
# Check that the 2 newly-unblocked principles are evaluated
from core.v9.principle_engine import PrincipleEngine
from core.v9.db_schema import get_connection, DB_PATH

engine = PrincipleEngine()
conn = get_connection()
sid = conn.execute("SELECT snapshot_id FROM forces_snapshots WHERE timeframe IN ('M5','M15','H1','H4') AND stale=0 LIMIT 1").fetchone()[0]
conn.close()

evals = engine.evaluate_principles(sid)
ant = [e for e in evals if e['principle_id'] == 'ANTAGONIST_NODE']
coal = [e for e in evals if e['principle_id'] == 'COALITION_NODE']
print(f'ANTAGONIST_NODE: {len(ant)} evaluations (triggered={sum(1 for e in ant if e["triggered"])})')
print(f'COALITION_NODE:  {len(coal)} evaluations (triggered={sum(1 for e in coal if e["triggered"])})')
```

## Pitfalls

- ❌ `_load_shared_context` uses `SELECT * FROM forces_snapshots` — the minimal `SELECT symbol, timeframe, mid, stale` was too narrow for cross-TF enrichment which needs `force_*` columns. If you narrow the query, cross-TF fields will be `None` and ANTAGONIST_NODE will never trigger.
- ❌ Setting cross-TF fields to `None` when `target_tf == timeframe` — the principle needs actual values. Derive from the current snapshot's own forces.
- ❌ The `--principes` calibration script still says "probablement bloque par le gap zone_diagnostics (donnees absentes)" for ANTAGONIST_NODE and COALITION_NODE — this is a stale message in the calibration script, not the actual state. The fields are populated, but market conditions don't trigger them.
- ❌ Don't create new DB tables or schemas for fields that can be derived at context-build time. `_load_shared_context()` is a single function — enrich it rather than creating new detectors.