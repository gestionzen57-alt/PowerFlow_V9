---
name: powerflow-bridge-watch
category: mlops
description: "Surveillance live du Bridge V8 — détection STALE Gate + alerte preemptive"
trigger: tick_sync_daemon zombie OU bridge_verdict STALE >3 cycles OU tick_sync_age >90s
tools_needed: [terminal, execute_code, search_files]
statut: legacy-v8
derniere_maj: 2026-07-09
version: 0.0.1
---
## 🎯 OBJECTIF

Surveiller en continu la santé du Bridge Tick (port 3001) et alerter AVANT la rupture du pipeline.

## 📊 MÉTRIQUES CLÉS

| Métrique | Seuil CRITIQUE | Seuil WARNING |
|----------|----------------|---------------|
| `tick_sync_age` | >120s | >60s |
| `bridge_verdict` | STALE >5 cycles | STALE >3 cycles |
| `last_bridge_push` | >2min | >90s |
| `decisions sans MTF` | >3 | >1 |

## 🔍 COMMANDS DE SURVEILLANCE

### Quick health check

```bash
# Âge dernier tick
python -c "from core.mcp_live_snapshot import get_live_snapshot; s=get_live_snapshot(); print(f'Âge tick: {s.get(\"tick_sync_age\", \"N/A\")}s')"

# Bridge verdict
grep "bridge_verdict" logs\tick_sync.log | tail -10
```

### Script watchdog (à lancer en Cron)

```python
# scripts/bridge_watchdog.py
import urllib.request
import json
import sys
from datetime import datetime

GATEWAY_URL = "http://127.0.0.1:8765"
MAX_TICK_AGE = 90  # secondes
MAX_STALE_CYCLES = 3

def check_bridge_health():
    try:
        req = urllib.request.urlopen(f"{GATEWAY_URL}/health", timeout=5)
        data = json.loads(req.read())
        
        tick_age = data.get('bridge', {}).get('tick_sync_age', 999)
        stale_count = data.get('bridge', {}).get('stale_cycles', 0)
        
        if tick_age > MAX_TICK_AGE:
            print(f"🚨 CRITIQUE: tick_sync_age={tick_age}s (max={MAX_TICK_AGE}s)")
            return 1
        elif stale_count > MAX_STALE_CYCLES:
            print(f"⚠️  WARNING: STALE pendant {stale_count} cycles")
            return 1
        else:
            print(f"✅ Bridge OK: tick_age={tick_age}s, stale_cycles={stale_count}")
            return 0
    except Exception as e:
        print(f"🚨 ERREUR: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(check_bridge_health())
```

## 🚨 SCÉNARIOS DE RUPTURE

### 1. STALE Gate (week-end ou panne)

**Symptômes :**
- `bridge_verdict: STALE` pendant >3 cycles
- `tick_sync_age` augmente progressivement
- pf_analyst retourne `htf_read=NULL`

**Action :**
```bash
# Weekend normal → ne rien faire (marché fermé)
# Semaine  → Redémarrer bridge
python scripts/feed_tick_force_minute.py
```

### 2. Tick Sync Daemon Zombie

**Symptômes :**
- Processus `tick_sync_daemon.py` visible mais âge tick >120s
- Logs silencieux >2min

**Action :**
```bash
# Tuer et redémarrer
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *tick_sync*"
python scripts/tick_sync_daemon.py
```

### 3. Rupture JSON pf_analyst

**Symptômes :**
- `reason=""` dans décisions
- `htf_read=NULL` OU `ltf_read=NULL`

**Action :**
→ Exécuter skill `powerflow-patch-p0`

## 📋 CRON JOB RECOMMANDÉ

```yaml
# À ajouter via hermes cronjob create
name: bridge-watchdog
schedule: 5m  # Toutes les 5 minutes
script: scripts/bridge_watchdog.py
deliver: telegram  # ou origin
```

## 🔗 LIENS

- Skill complémentaire: `powerflow-patch-p0`
- Doc: `docs/TICK_PIPELINE.md`
- Script: `scripts/feed_tick_force_minute.py`