# ZCODE RESUME PROMPT — V10 S25-OMEGA Full-Stack

**Mise à jour :** 2026-08-10 08:02 CEST — Perplexity CEO No-Limit

Ce fichier est le point d'entrée de reprise pour tout agent (ZCode, Hermes, Nemotron, Perplexity).

---

## 📍 État courant — Lundi 10/08 08:02 CEST

| Champ | Valeur |
|---|---|
| Branche ZCode active | `feat/replay-fullstack-v10` |
| Branche base | `feat/v9-foundation-clean` |
| HEAD replay (origin) | `e2fcb3a` (C10 Walk-Forward+LiveGate) |
| HEAD Hermes local | `d88787e` (réconciliation R2 — 2 commits non pushés) |
| Tests V10 | **1290/1310** (20 échecs dette API C9 — fix Hermes en cours) |
| Replay status | **FULLSTACK_V10** — pipeline C1→C10 branché |
| Sprint actif | **S25-OMEGA** |
| ZCode status | **EN COURS** — run_all() en exécution |
| Ingestion live | ✅ port 31685 PID 2600, max_ts 05:29 UTC |
| Trou données | ⚠️ capture mort vendredi → relancé lundi matin — à vérifier |

---

## 🚨 Contexte d'intégration — À lire avant run_all()

**Hermes a résolu une dette d'intégration majeure ce matin :**
- 49 erreurs de collection pytest → 1290/1310 (Hermes commit `d88787e`)
- 4 modules réconciliés R2 : `v10_bayesian_recalibrator`, `v10_rl_adapter`, `v10_risk_shield`, `v10_error_learner`
- `__init__.py` réparé (imports morts `ADWINLikeDrift`, `ShieldResult`)
- API legacy C9 coexist avec API origin C10 (additif R2 strict)

**Implication pour ZCode :** le pipeline est fonctionnel. Lance run_all() normalement.

---

## 🎯 Mission immédiate ZCode

1. **Diagnostic DB** : lire colonnes réelles de `forces_snapshots` + détecter trou 08-09/08
2. **Replay Full-Stack** : `engine.run_all()` sur 8 paires × M30/H1
3. **Rapport structuré** : JSON complet → `reports/zcode_fullstack_report.json`
4. **LearningLoop** : `loop.run_cycle()` si temps disponible
5. **Recommandations** : top 3 paires edge + modules manquants + verdict trou données

---

## 📚 Documents clés

- `HERMES_PROMPT_MAX.md` — prompt complet Hermes parallèle (**généré ce matin**)
- `ZCODE_PROMPT.md` — prompt complet ZCode Full-Stack (**lire en premier**)
- `core/v10/v10_replay_engine.py` — moteur replay (commit `e2fcb3a` + patches Hermes)
- `docs/V10/STATE.md` — pipeline complet
- `docs/V10/CACHE_BOARD.md` — snapshot live
- `reports/` — rapports JSON générés automatiquement

---

## ⚠️ Vérification trou de données (OBLIGATOIRE avant run_all)

```python
import sqlite3, pandas as pd
conn = sqlite3.connect('data/powerflow.db')  # adapter chemin
df = pd.read_sql("""
    SELECT DATE(bar_time) as date, COUNT(*) as n_bars
    FROM forces_snapshots
    WHERE bar_time > '2026-08-07'
    GROUP BY DATE(bar_time) ORDER BY 1
""", conn)
print(df)
conn.close()
# Si n_bars < 200 pour 2026-08-08 ou 2026-08-09 → ajouter dans rapport JSON :
# "data_gap": {"dates": ["2026-08-08", "2026-08-09"], "severity": "HIGH"}
```

---

## 🛡️ Doctrine active

| Règle | Status |
|---|---|
| R1-AGIR | ✅ action directe sans validation |
| R2 additif pur | ✅ 0 modification modules existants |
| R6-fail-open | ✅ fallback CS proxy si module manquant |
| R9-AUDIT | ✅ JSON rapport complet |
| R10-CAPITAL | ✅ 0 ordre réel — FULLSTACK_V10 only |

---

## ⚡ Lancement immédiat

```bash
# Sur VPS / local
git checkout feat/replay-fullstack-v10
git pull origin feat/replay-fullstack-v10

python -c "
import json
from core.v10.v10_replay_engine import ReplayEngine
engine = ReplayEngine(db_path='data/powerflow.db')
report = engine.run_all()
with open('reports/zcode_fullstack_report.json', 'w') as f:
    json.dump(report, f, indent=2, default=str)
print('DONE — voir reports/zcode_fullstack_report.json')
print('WR global:', report.get('summary', {}).get('global_wr'))
print('PnL global:', report.get('summary', {}).get('global_pnl_net'))
"

# Renvoyer le contenu de zcode_fullstack_report.json à Perplexity
```

---

## 📊 Format rapport à renvoyer à Perplexity

Voir section **"Format du rapport à renvoyer à Perplexity"** dans `ZCODE_PROMPT.md`.

**Ajouter obligatoirement dans le JSON :**
```json
"data_gap_audit": {
  "dates_checked": ["2026-08-07", "2026-08-08", "2026-08-09", "2026-08-10"],
  "bars_per_day": {"2026-08-07": 0, "2026-08-08": 0, "2026-08-09": 0, "2026-08-10": 0},
  "gap_detected": false,
  "gap_severity": "NONE|LOW|HIGH",
  "recommendation": "..."
}
```

Perplexity orchestrera ensuite :
- Analyse comparative paires (edge detector)
- Décision merge `feat/v9-foundation-clean` → `feat/replay-fullstack-v10`
- Validation DeploymentValidator C20 (12 critères GO LIVE)
- Décision R10 : levée ou maintenue

---

*Mis à jour par Perplexity CEO No-Limit — 2026-08-10 08:02 CEST*
