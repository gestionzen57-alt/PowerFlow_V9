---
name: powerflow-pattern-signal-tracker
description: Track pattern clusters → document after-signal outcomes → persist scene memory for RAG/learning + papertrade backtest
category: trading
tags: [powerflow, patterns, signal-tracking, rag, papertrade, scene-memory]
version: 1.0.0
---

# PowerFlow Pattern Signal Tracker Skill

## Purpose
Tracks what happens AFTER pattern clusters are detected — closes the feedback loop between pattern detection and market outcome. Persists full scene context (patterns, zones, coalitions, temporal sequence) for RAG retrieval and papertrade strategy backtesting.

## When to Use
- After pattern detection runs (detected_patterns table populated)
- During live session to monitor signal quality in real-time
- For historical analysis of pattern accuracy
- Before papertrade strategy development — need scene memory dataset

## Prerequisites
- `core/powerflow_fresh.db` with tables: `detected_patterns`, `structure_ledger`, `force_snapshots_v2`
- Python 3.11+ with sqlite3, json, datetime
- Hermes profile `powerflow` active

## Files
- `scripts/pf_pattern_signal_tracker.py` — main tracker script
- `scripts/pf_h1_cross_watcher.py` — H1 cross detection watcher
- `core/powerflow_fresh.db` — source data
- `pattern_scene_memory` table — auto-created RAG storage

## Workflow

### 1. Run Tracker Once (Live Analysis)
```bash
cd D:/Projet/V8
python scripts/pf_pattern_signal_tracker.py --once
```
Outputs cluster-by-cluster analysis + summary + persists to `pattern_scene_memory`.

### 2. Run Tracker Loop (Background Monitoring)
```bash
python scripts/pf_pattern_signal_tracker.py --loop --poll 300
```
Runs every 5 minutes, silent between alerts.

### 3. Run H1 Cross Watcher (Scalping Trigger)
```bash
python scripts/pf_h1_cross_watcher.py --once
python scripts/pf_h1_cross_watcher.py --loop --poll 300 --quiet
```
Detects: `cross_done` (pullback post-cross), `cross_imminent_short` (reversal imminent), `GBP_EXHAUSTION` pattern.

### 4. Query Scene Memory for RAG
```python
import sqlite3, json
conn = sqlite3.connect('core/powerflow_fresh.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('''
    SELECT cluster_ts, pattern_names, pattern_types, zones_m5, zones_m15, zones_h1, zones_h4,
           coalition_forces, temporal_sequence, predicted_direction, actual_direction, outcome, wr
    FROM pattern_scene_memory
    WHERE outcome = "CONFIRMED" AND wr > 0.5
    ORDER BY cluster_ts DESC LIMIT 20
''').fetchall()
for r in rows:
    print(json.loads(r['pattern_names']), json.loads(r['pattern_types']), r['outcome'], r['wr'])
```

## Pattern Classification (Critical)

### SIGNAL_DIRECTIONNEL — Genuine directional votes
- BULLISH_DIVERGENCE, BEARISH_DIVERGENCE
- GBP_EXHAUSTION, USD_EXHAUSTION
- CONSTRUCTION_GBP_LEAD, CONSTRUCTION_USD_LEAD
- ZONE_BATTLE_CHARGE_GBP_LEAD, ZONE_BATTLE_CHARGE_USD_LEAD
- REJECTION_4_PHASES, META_3_ACTES, PRE_REJECTION_CROSS

### MICROSTRUCTURE_ANNOTATION — Context only, NO directional vote
- BOLLINGER_SQUEEZE, VOLATILITY_REGIME_CHANGE
- MOMENTUM_SHIFT, ACCELERATION_DETECT
- STRUCTURE_IMBRICATION, MULTI_TF_ALIGNMENT

### ANOMALY_FLAG — Warning, not prediction
- CROSS_COORD_MAJORS, CROSS_COORD_M15, CROSS_COORD_ALL
- COALITION_USD, COALITION_NON_USD, COALITION_MAJORS
- OPPOSITION_DETECTED, PINCH

## Scene Memory Schema
```sql
CREATE TABLE IF NOT EXISTS pattern_scene_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_ts TEXT NOT NULL,
    pattern_names TEXT,          -- JSON array
    pattern_types TEXT,           -- JSON array (SIGNAL_DIRECTIONNEL / MICROSTRUCTURE_ANNOTATION / ANOMALY_FLAG)
    pattern_confidences TEXT,     -- JSON array
    zones_m5 TEXT,                -- JSON: current zone M5
    zones_m15 TEXT,
    zones_h1 TEXT,
    zones_h4 TEXT,
    coalition_forces TEXT,        -- JSON: {gbp: X, usd: Y, eur: Z, ...}
    temporal_sequence TEXT,       -- JSON: [{tf, event, ts}, ...]
    predicted_direction TEXT,    -- LONG / SHORT / NEUTRAL
    actual_direction TEXT,       -- filled after resolution
    outcome TEXT,                 -- CONFIRMED / CONTRADICTED / PENDING / STALE
    wr REAL,                      -- rolling win-rate for pattern combo
    pips_moved REAL,
    resolved_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

## Limits
- Resolution window: 30min to 4h after cluster (configurable)
- Pattern classification is hardcoded — no ML classification yet
- Scene memory is local DB only (not synced to ChromaDB — future enhancement)
- Direct DB read (no MCP) — by design for speed

## Triggers (Hermes)
- "track patterns" / "analyse signaux" / "cluster outcomes"
- "scene memory" / "pattern accuracy" / "signal quality"
- "track what happened after pattern X"
