---
name: powerflow-patch-p0
category: mlops
description: "PATCH P0 — Fix critique pf_analyst + gateway hermes_code (rupture 20 juin 2026)"
trigger: pf_analyst retourne htf_read=NULL OU ltf_read=NULL OU reason="" pendant >3 cycles
tools_needed: [terminal, read_file, patch, execute_code]
statut: legacy-v8
derniere_maj: 2026-07-09
version: 0.0.1
---
## 🎯 OBJECTIF

Rétablir le pipeline de décision PowerFlow V8 après une rupture de type "STALE Gate" ou "JSON vide".

## 🔍 DIAGNOSTIC RAPIDE

```bash
# 1. Vérifier logs pf_analyst
grep "EMPTY_REASON\|JSON parse error" logs\autopilot_live.log | tail -20

# 2. Vérifier gateway
curl http://127.0.0.1:8765/health | jq .agents

# 3. Vérifier agent_registry.py
grep -A5 "hermes_code" federation\agent_registry.py
```

## 🛠️ ACTIONS CORRECTIVES

### Étape 1 : Patch `pf_analyst.py` (guardrails JSON)

```python
# Fichier: core/pf_analyst.py
# Lignes à patcher : _parse_compact_json() + try/except bloc gateway call
```

### Étape 2 : Patch `agent_registry.py` (hermes_code → qwen3-coder-next:cloud)

```yaml
# Fichier: federation/agent_registry.py
hermes_code:
  model: qwen3-coder-next:cloud  # était: kimi-k2.7-code
  requests_per_hour: 120         # était: 60
```

### Étape 3 : Redémarrer gateway + vider cache

```bash
# Tuer gateway
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *gateway*"

# Vider cache Python
Remove-Item -Recurse -Force __pycache__  # ou rmdir /s /q __pycache__

# Redémarrer
python federation/gateway_server.py
```

### Étape 4 : Test validation

```python
from core.pf_analyst import get_decision
result = get_decision(test_snapshot)
assert result['htf_read'] is not None
assert result['ltf_read'] is not None
assert 'GO' in result['verdict'] or 'WAIT' in result['verdict'] or 'NO' in result['verdict']
```

## 📋 CHECKLIST POST-PATCH

- [ ] Gateway redémarré avec nouvelle config
- [ ] 10 cycles consécutifs avec htf_read + ltf_read non-NULL
- [ ] WR partiel > 60% sur 1h
- [ ] Zéro alerte EMPTY_REASON dans logs
- [ ] Checkpoint créé: `docs/checkpoints/CHECKPOINT_YYYY_MM_DD_PATCH_P0.md`
- [ ] STATE.md + JOURNAL.md mis à jour
- [ ] Commit + push auto via `scripts/aaa.py`

## ⚠️ PIÈGES CONNUS

1. **Cache Python** : Toujours vider `__pycache__` avant redémarrage gateway
2. **Gateway timing** : Patch MUST être fait AVANT redémarrage gateway
3. **GATEWAY_AGENT** : Doit pointer vers `hermes_code` (pas `hermes_free4`)
4. **Week-end** : Marché fermé ven 23h → dim 23h UTC → WAIT normaux

## 🔗 LIENS

- Checkpoint: `docs/checkpoints/CHECKPOINT_2026_06_22_PATCH_P0.md`
- Commit: `ae63f82` — `fix(pf_analyst): PATCH P0`
- Doc: `docs/DOCTRINE_LECTURE_MARCHE.md`