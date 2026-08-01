---
name: powerflow-h1-cross-watcher
description: Real-time H1 leadership cross detector for scalping — cross_done (pullback post-cross), cross_imminent_short (reversal), GBP_EXHAUSTION pattern, M5 exhaustion, H1 bar close countdown
category: trading
tags: [powerflow, h1-cross, scalping, watcher, gbp-exhaustion, mcp-hot]
version: 1.0.0
statut: actif-v9
derniere_maj: 2026-07-31
---

# PowerFlow H1 Cross Watcher Skill

## Purpose
Real-time H1 cross detector for GBPUSD scalping. Detects leadership changes between GBP/USD on H1 timeframe, aligned with M5 exhaustion and H1 bar close for high-conviction entries.

## When to Use
- Live London/NY session monitoring
- Scalping entries on H1 leadership change
- Hedge/partial profit on M5 exhaustion against H1 trend
- Telegram alerts for cross_done / cross_imminent_short

## Prerequisites
- `core/powerflow_fresh.db` with tables: `structure_ledger`, `detected_patterns`, `bridge_forces_tick`, `force_snapshots_v2`, `cinematic_metrics`
- Python 3.11+ with sqlite3
- Hermes profile `powerflow` active
- Telegram bot token in `.env` for alerts

## Files
- `scripts/pf_h1_cross_watcher.py` — main watcher script
- `core/powerflow_fresh.db` — source data (NOT MCP, direct DB read)

## Workflow

### 1. Run Once (Check Current State)
```bash
cd D:/Projet/V8
python scripts/pf_h1_cross_watcher.py --once
```

### 2. Run Loop (Background Monitoring)
```bash
python scripts/pf_h1_cross_watcher.py --loop --poll 300 --quiet
```
- Polls every 5 minutes (300s)
- `--quiet` = no output unless alert condition met
- Sends Telegram alert on signal

### 3. Cron Job (Production)
```bash
hermes cronjob create --name "PF-H1-Cross-Watcher" \
  --schedule "0 7 * * *" \
  --script "scripts/pf_h1_cross_watcher.py" \
  --args "--loop --poll 300 --quiet" \
  --no-agent --deliver telegram
```

## Detection Logic

### cross_done (Pullback Post-Cross)
- **H1**: GBP leader (h1_gbp > h1_usd)
- **M5**: delta_f > 40 (ZONE EXTREME BUY = GBP exhaustion)
- **Signal**: SHORT (partial profit/hedge — GBP up move exhausted, pullback expected)
- **Bridge**: SHORT confirms

### cross_imminent_short (Reversal Imminent)
- **H1**: USD leader (h1_usd > h1_gbp)
- **M5**: delta_f > 40 ZONE EXTREME BUY (GBP exhaustion while USD leads H1)
- **Signal**: SHORT (reversal imminent — GBP can't sustain, USD will cross)
- **Bridge**: SHORT or WAIT

### GBP_EXHAUSTION Pattern (New)
- Detected when M5 delta_f > 40 in direction of current H1 leader
- Indicates momentum exhaustion at extreme
- Often precedes H1 cross or pullback

### M5 Exhaustion Calculation
```python
m5_delta_f = abs(m5_gbp - m5_usd)  # from structure_ledger.m5_delta_f
if m5_delta_f > 40:
    m5_zone_extreme = True
```

### H1 Bar Close Countdown
- Calculates seconds until next H1 bar close
- Signals aligned with bar close have higher conviction
- Display format: `H1 close in X:YY`

## Alert Priority
| Signal | Priority | Action |
|--------|----------|--------|
| `cross_done` | HIGH | Enter SHORT / partial profit LONG |
| `cross_imminent_short` | CRITICAL | Prepare reversal entry |
| `GBP_EXHAUSTION` | MEDIUM | Monitor, do NOT enter same direction |
| M5 exhaustion | LOW | Context annotation only |

## Data Sources (Direct DB)
```sql
-- H1 leadership
SELECT gbp_force, usd_force FROM force_snapshots_v2
WHERE timeframe = 'H1' ORDER BY created_at DESC LIMIT 1;

-- M5 delta
SELECT m5_delta_f, m5_gbp, m5_usd FROM structure_ledger
ORDER BY created_at DESC LIMIT 1;

-- Bridge confirmation
SELECT signal FROM bridge_forces_tick
ORDER BY created_at DESC LIMIT 1;
```

## Limits
- GBPUSD only (single pair)
- H1+M5 timeframes only
- No backtesting integration yet (manual comparison)
- Direct DB read — no MCP by design (latency)
- Requires MT4 tick data flowing for bridge confirmation

## Integration Points
- **MCP 3110 (hot)**: `get_live_snapshot` for additional context
- **MCP 3130 (learning)**: Signal outcomes feed back into learned rules
- **pattern_scene_memory**: Cross events persisted for RAG analogies
- **Telegram**: Alerts delivered via `pf_telegram_bridge.py`

## Triggers (Hermes)
- "watch H1 cross" / "cross imminent" / "leadership change"
- "GBP exhaustion" / "M5 exhaustion" / "delta extreme"
- "scalping setup" / "H1 bar close"
- "cross_done" / "cross_imminent_short"
