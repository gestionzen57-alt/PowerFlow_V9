---
name: powerflow-live-capture-queue
description: Capture instantanée live → queue → traitement différé. Jamais de latence pendant le trading.
category: trading
tags: [powerflow, live, capture, queue, async, low-latency]
version: 1.0.0
---

# PowerFlow Live Capture Queue Skill

## Purpose
Capture une observation live **instantanément** (<1s) sans aucun traitement. L'agent enregistre dans la queue et continue. Le traitement (enrichissement marché, classification, délégation) est fait **en background** par le worker.

## Core Principle
```
Tu parles (live)  →  CAPTURE (<1s)  →  WORKER (background)  →  RESULTAT dispo
                        ↑ ZÉRO LATENCE ICI
```

**NE JAMAIS traiter une capture en sync pendant le live.**
Si l'utilisateur est en session live → capturer → passer à la suite.

## When to Use
- Pendant une session de trading live
- Quand l'utilisateur décrit une observation marché en temps réel
- Quand l'utilisateur demande "note ça" / "capture" / "enregistre"
- Quand plusieurs observations rapides se suivent
- Quand l'utilisateur est pressé ("vite", "note juste")

## When NOT to Use
- Recherche historique (→ `powerflow-pattern-signal-tracker`)
- Analyse approfondie post-session (→ `powerflow-weekly-analysis`)
- Backtest / replay (→ `powerflow-papertrade-replay`)

## Prerequisites
- `core/agent_bus.db` (auto-created `live_captures` table)
- Python 3.11+ with sqlite3
- Hermes profile `powerflow` active

## Files
- `scripts/pf_live_capture.py` — capture CLI (<1s)
- `scripts/pf_live_capture_worker.py` — background worker (traitement différé)
- `core/agent_bus.db` — queue storage

## Workflow

### 1. Capturer une observation (JAMAIS de traitement inline)
```bash
# Syntaxe minimale — le plus rapide possible
python scripts/pf_live_capture.py "GBP en force H1, M5 exhaustion delta 45"

# Avec tag et priorité
python scripts/pf_live_capture.py --tag scalping --priority high "cross imminent short"

# Observation simple
python scripts/pf_live_capture.py --tag observation "USD reprend sur H4"
```

### 2. Vérifier la queue (pas de capture)
```bash
python scripts/pf_live_capture.py --list
python scripts/pf_live_capture.py --stats
```

### 3. Lancer le worker en background (UNE FOIS par session)
```bash
python scripts/pf_live_capture_worker.py --loop --poll 60 &
# ou dans un terminal séparé
start /B python scripts/pf_live_capture_worker.py --loop --poll 60 --verbose
```

### 4. Worker avec délégation Hermès (advanced)
```bash
python scripts/pf_live_capture_worker.py --loop --poll 60 --hermes-delegate
```
Chaque capture est envoyée au skill Hermès approprié en sous-processus.

## Capture → Worker → Delegate Pipeline

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐
│ CAPTURE     │     │ WORKER       │     │ DELEGATE      │
│ (sync <1s)  │────►│ (bg 60s)     │────►│ (sous-agent)  │
│             │     │              │     │               │
│ raw_text    │     │ 1. Classify  │     │ skill=watcher │
│ tag         │     │ 2. Enrich    │     │ skill=tracker │
│ priority    │     │ 3. Route     │     │ skill=analyst │
│             │     │ 4. Delegate   │     │               │
└─────────────┘     └──────────────┘     └───────────────┘
```

## Tag → Worker Routing

| Tag | Classification | Délègue à |
|-----|--------------|-----------|
| `scalping` | actionable | `powerflow-h1-cross-watcher` |
| `cross` | actionable | `powerflow-h1-cross-watcher` |
| `exhaustion` | actionable | `powerflow-h1-cross-watcher` |
| `pattern` | actionable | `powerflow-pattern-signal-tracker` |
| `alert` | actionable | `powerflow-trader` |
| `trade_idea` | actionable | `powerflow-papertrade-replay` |
| `zone` | actionable | `powerflow-lecture-structurelle` |
| `coalition` | actionable | `powerflow-analyst` |
| `bridge` | actionable | `powerflow-bridge-patch` |
| `construction` | actionable | `powerflow-pattern-engineering` |
| `observation` | info | **pas de délégation** |
| `note` | info | **pas de délégation** |

## Classification Rules

Le worker classe automatiquement :
- **actionable** : tag scalping/cross/alert → délégation immédiate
- **actionable_research** : text contient "check", "verify", "WR", "backtest", "historique"
- **info** : tag observation/note → enrichissement only, pas de délégation

## Auto-Enrichment (Worker)
Le worker enrichit chaque capture avec :
- Snapshot H1 forces (GBP/USD/EUR/CHF)
- Structure ledger (M5 delta, H1/H4 verdicts)
- Bridge signal
- Patterns récents (<15min)

## Triggers (Hermes)
- "capture" / "note ça" / "enregistre" / "capte"
- "vit" / "vite" / "quick" (en contexte live)
- "queue" / "file d'attente"
- "worker" / "traite la queue"

## Limits
- DB local only (sqlite3 WAL)
- Pas de sync multi-session (single writer)
- Max ~500 captures/jour (conservateur)
- Auto-extract context est basique (keywords, pas NLP)

## Anti-Pattern (NE JAMAIS FAIRE)
```python
# ❌ MAUVAIS : traitement sync pendant le live
capture = user_text
analysis = run_full_analysis(capture)  # 10-30s perdues!
print(analysis)

# ✅ BON : capture instantanée, traitement différé
capture_id = live_capture(user_text)  # <1s
print(f"📝 Capture #{capture_id} enregistrée. Worker traite en bg.")
# L'utilisateur continue immédiatement
```
