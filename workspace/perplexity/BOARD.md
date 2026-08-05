# BOARD — PowerFlow V10
_Dernière mise à jour : 2026-08-05 11:37 CEST — Session Perplexity_

---

## 🎯 Mission active
Construire le pipeline edge fund quantique V10 aligné sur la logique Fatman (indicateur éditeur).

## ✅ Acquis confirmés
- Architecture V9 stable : 54 tests verts sur `feat/v9-foundation-clean`
- Compréhension Fatman complète : logique calcul scores devise reverse-engineerée
- 6 TF validés : M1 / M5 / M15 / **M30** (ajouté) / H1 / H4
- Dualité MT4 (Tickmill) + MT5 (Tickmill) documentée
- Grille signaux × levier établie (6 setups)
- Plan action Hermes rédigé → `docs/HERMES_PLAN_V10.md`

## 🔴 Gap prioritaire #1
`v10_currency_strength.py` — module scores devise — ABSENT du repo
→ Tout le pipeline en dépend. Rien d'autre ne peut avancer sans lui.

## 🔴 Gap prioritaire #2
M30 absent des modules `v10_force.py`, `v10_structure.py`, `v10_context.py`
→ À injecter après currency_strength validé (≥15 tests verts)

## ❄️ Gelé (doctrine)
- Phase 10 fédération d'agents
- Skills auto-générés
- Architecture routing modèles / mémoire avancée

## 📌 Prochaine action Hermes
```
Créer core/v10/v10_currency_strength.py
→ 15 tests minimum
→ Commit atomique sur feat/v9-foundation-clean
→ Rapport résultats avant toute autre étape
```

## 🗂️ Fichiers pivots
| Fichier | Rôle |
|---|---|
| `docs/STATE.md` | Source de vérité vivante |
| `docs/CACHE_BOARD.md` | Tableau de reprise complet |
| `docs/ROADMAP.md` | Phases gelées |
| `docs/DOCTRINE.md` | Règles immuables |
| `docs/HERMES_PLAN_V10.md` | Plan d'action edge fund quantique |
| `workspace/perplexity/BOARD.md` | Ce fichier — synthèse rapide |
| `workspace/perplexity/ACTIVE_TASKS.md` | Tâches actives |
| `workspace/perplexity/memory/DECISIONS_LOG.md` | Log décisions |
