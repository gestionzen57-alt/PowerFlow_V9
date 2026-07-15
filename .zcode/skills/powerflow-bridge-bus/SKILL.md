---
name: powerflow-bridge-bus
description: "Pont bidirectionnel entre agents PowerFlow via table agent_event_bus — synchronisation décisions/outcomes inter-daemons"
version: 1.0.0
author: powerflow-m3-align
tags: [powerflow, bridge, bus, event-driven, inter-daemon]
statut: legacy-v8
derniere_maj: 2026-07-09
---
# Powerflow Bridge Bus

# PowerFlow Bridge Bus

## Rôle
Pont bidirectionnel entre daemons PowerFlow (analyst, autopilot, bridge feeder, learning). Communication asynchrone via SQLite `agent_event_bus`.

## Quand charger
- Incident : bus vide ou events non consommés.
- Ajout nouveau daemon producteur/consommateur.
- Diagnostic : pourquoi trade pas ouvert alors que décision prise ?

## Table `agent_event_bus`
```sql
CREATE TABLE agent_event_bus (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,           -- epoch ms
    producer TEXT NOT NULL,        -- 'analyst' | 'bridge' | 'autopilot' | 'learning'
    event_type TEXT NOT NULL,      -- 'DECISION' | 'OUTCOME' | 'PATTERN' | 'ALERT'
    payload TEXT NOT NULL,         -- JSON
    consumed_by TEXT,              -- NULL = pending, 'autopilot' = traité
    correlation_id TEXT            -- lien décision→outcome
);
```

## Workflow type
```
bridge feeder (M1 ticks) → bus DECISION
analyst (M5 cross) → bus DECISION (corrélation_id=123)
autopilot paper_trade → consomme → bus OUTCOME (corrélation_id=123)
learning_cycle → consomme OUTCOME → update rules
```

## Bridge M3 critique (vérifier à chaque reprise)
```bash
# À lancer en background
python core/pf_hermes_dispatcher.py --loop --poll 2.0 &
# Keep-alive
python scripts/run_bridge_feeders_loop.py &
```

Sans bridge → bus producer vide → 0 décision → 0 outcome → learning_loop mort.

## Diagnostic
- `SELECT COUNT(*) FROM agent_event_bus WHERE consumed_by IS NULL` → backlog.
- Si backlog > 100 → consumer (autopilot) probablement crashé.
- `SELECT producer, COUNT(*), MAX(ts) FROM agent_event_bus GROUP BY producer` → qui parle ?

## Pièges
- Oublier `correlation_id` → impossible de lier décision à outcome → learning cassé.
- Bus WAL mode désactivé → race conditions entre daemons.
- `consumed_by='autopilot'` écrit AVANT traitement → outcome jamais créé.

