---
name: powerflow-live-delegate-worker
description: Background worker qui traite la capture queue et délègue aux sous-agents spécialisés (watcher, tracker, analyst, trader)
category: trading
tags: [powerflow, worker, delegate, background, async, pipeline]
version: 1.0.0
statut: actif-v9
derniere_maj: 2026-07-31
---

# PowerFlow Live Delegate Worker Skill

## Purpose
Traite la queue de captures en background et délègue chaque capture au sous-agent/skill approprié. C'est le **moteur de traitement différé** du système live-capture-queue.

## When to Use
- Au démarrage d'une session live (lancer en background)
- Quand la queue contient des captures non traitées
- Pour vérifier ce que le worker a traité

## Prerequisites
- `scripts/pf_live_capture_worker.py` créé et fonctionnel
- `core/agent_bus.db` avec table `live_captures`
- `core/powerflow_fresh.db` pour enrichissement marché
- Skills cibles installés (watcher, tracker, analyst, etc.)

## Files
- `scripts/pf_live_capture_worker.py` — le worker
- `core/agent_bus.db` — queue + tasks
- `core/powerflow_fresh.db` — market context enrichment

## Workflow

### 1. Lancer le worker (début de session live)
```bash
# Terminal 1 : worker boucle
python scripts/pf_live_capture_worker.py --loop --poll 60 --verbose

# Terminal 2 : tes captures
python scripts/pf_live_capture.py "observation live..."

# Terminal 3 : optionnel — délégation hermes
python scripts/pf_live_capture_worker.py --loop --poll 60 --hermes-delegate
```

### 2. Traitement unique (test)
```bash
python scripts/pf_live_capture_worker.py --once --verbose
```

### 3. Vérifier les tâches déléguées
```sql
-- Tâches créées par le worker
SELECT id, assigned_to, status, priority, title, created_at
FROM tasks
WHERE session_id IS NOT NULL
ORDER BY created_at DESC LIMIT 20;

-- Captures traitées
SELECT id, tag, status, delegated_to, created_at, processed
FROM live_captures
ORDER BY created_at DESC LIMIT 20;
```

## Worker Pipeline

```
Pour chaque capture en attente:

  1. CLASSIFY
     ├─ tag ∈ {scalping, cross, alert} → actionable
     ├─ text contient "check/WR/backtest" → actionable_research
     └─ tag ∈ {observation, note} → info

  2. ENRICH (si ≠ info)
     ├─ Snapshot H1 forces (powerflow_fresh)
     ├─ Structure ledger (m5_delta_f, verdicts)
     ├─ Bridge signal
     └─ Patterns récents (<15min)

  3. ROUTE + DELEGATE
     ├─ hermes-delegate=ON → sous-processus hermes skill
     └─ hermes-delegate=OFF → task dans agent_bus.tasks

  4. MARK DONE
     └─ processed=1, status='done'
```

## Delegate Mapping

| Capture Tag | Target Skill | Action |
|-------------|-------------|--------|
| scalping | h1-cross-watcher | Vérifie cross + exhaustion |
| cross | h1-cross-watcher | Détecte cross_done / cross_imminent |
| exhaustion | h1-cross-watcher | Calcule M5 delta + zone |
| pattern | pattern-signal-tracker | Cluster analysis + scene memory |
| alert | trader | Score decision + trade setup |
| trade_idea | papertrade-replay | Backtest rapide de l'idée |
| zone | lecture-structurelle | Analyse multi-TF zones |
| coalition | analyst | Snapshot coalition + forces |
| bridge | bridge-patch | Vérifie signal bridge |
| construction | pattern-engineering | Engineering pattern |
| observation | *(aucun)* | Archive enrichie only |
| note | *(aucun)* | Archive enrichie only |

## Monitoring

### Stats en temps réel
```bash
python scripts/pf_live_capture.py --stats
python scripts/pf_live_capture.py --list
```

### Purge captures traitées (>24h)
```bash
python scripts/pf_live_capture.py --flush
```

### Performance cible
- Capture: <1s (sqlite insert)
- Worker cycle: <2s par capture (enrichissement + route)
- Poll interval: 60s (configurable)
- Max queue depth: 500 captures

## Triggers (Hermes)
- "worker" / "traite" / "process queue"
- "délègue" / "delegate"
- "queue status" / "capture stats"

## Integration
- **agent_bus.tasks**: les tâches déléguées sont créées ici
- **agent_bus.messages**: les résultats peuvent être publiés ici
- **Telegram**: notifications pour les captures actionable (via bridge)

## Limits
- Single-threaded (un seul worker à la fois)
- Pas de retry en cas d'échec de délégation
- Enrichissement DB peut échouer si powerflow_fresh.db locked
- hermes-delegate requiert hermes CLI dans le PATH
