# ZCODE RESUME PROMPT — V10 S25-OMEGA Full-Stack

**Mise à jour :** 2026-08-09 06:13 CEST — Perplexity GitHub MCP

Ce fichier est le point d'entrée de reprise pour tout agent (ZCode, Hermes, Nemotron, Perplexity).

---

## 📍 État courant

| Champ | Valeur |
|---|---|
| Branche active | `feat/replay-fullstack-v10` |
| Branche base | `feat/v9-foundation-clean` |
| HEAD replay | `62fd718` (ReplayEngine Full-Stack V10) |
| Tests V10 | **1310/1310 verts** (base) |
| Replay status | **FULLSTACK_V10** — 20 modules branchés |
| Sprint actif | **S25-OMEGA** |
| Action requise | **ZCode : lancer run_all() + rapport JSON** |

---

## 🎯 Mission immédiate ZCode

1. **Diagnostic DB** : lire colonnes réelles de `forces_snapshots`
2. **Replay Full-Stack** : `engine.run_all()` sur 8 paires × 2 TF
3. **Rapport structuré** : JSON complet → renvoyer à Perplexity
4. **LearningLoop** : `loop.run_cycle()` si temps disponible
5. **Recommandations** : top 3 paires edge + modules manquants

---

## 📚 Documents clés

- `ZCODE_PROMPT.md` — prompt complet ZCode Full-Stack (**lire en premier**)
- `core/v10/v10_replay_engine.py` — moteur replay (commit `62fd718`)
- `docs/V10/STATE.md` — pipeline complet
- `docs/V10/CACHE_BOARD.md` — snapshot live
- `reports/` — rapports JSON générés automatiquement

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

python -c "
import json
from core.v10.v10_replay_engine import ReplayEngine
engine = ReplayEngine(db_path='data/powerflow.db')
report = engine.run_all()
print(json.dumps(report, indent=2, default=str))
" > reports/zcode_fullstack_report.json 2>&1

# Renvoyer zcode_fullstack_report.json à Perplexity
```

---

## 📊 Format rapport attendu par Perplexity

Voir section **"Format du rapport à renvoyer à Perplexity"** dans `ZCODE_PROMPT.md`.

Perplexity orchestrera ensuite :
- Commit du rapport dans `reports/`
- Analyse comparative paires (edge detector)
- Ouverture PR vers `feat/v9-foundation-clean`
- Recommandations calibration

---

*Mis à jour par Perplexity GitHub MCP — 2026-08-09 06:13 CEST*
