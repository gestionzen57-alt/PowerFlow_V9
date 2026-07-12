# Carte de données — V9-trader-mini

- Généré : Brief O5 (2026-07-12), script `scripts/v9_export_dataset.py`.
- Prérequis : Brief O1 livré (labels DYNAMIC/SKIPPED propres, 0 décision TP_SL restante).

## Volumes par split

| Split | N | Wins | Losses | WR |
|---|---|---|---|---|
| train | 6595 | 5827 | 768 | 88.4% |
| val | 800 | 711 | 89 | 88.9% |
| test | 822 | 734 | 88 | 89.3% |
| **total DYNAMIC** | 8217 | 7272 | 945 | 88.5% |
| skipped (exclu train/val/test) | 1298 | — | — | — |

Erreurs de chargement de contexte (snapshot incomplet, exclu) : 0

## Distribution des classes

Déséquilibre attendu ~85-88% win (post-Brief O1, résolution DYNAMIC) — WR réel observé : 88.5%. Recommandation (non appliquée ici, décision d'entraînement séparée) : class weights ou sous-échantillonnage de la classe majoritaire (win) côté entraînement, pas de rééquilibrage dans l'export lui-même (le dataset doit rester fidèle à la distribution réelle).

## Biais connus

- **Période à drift haussier documenté (~91%)** — cf. `docs/reports/NY_AFTER_BIAS_20260712.md` §Brief O4. Un modèle entraîné sur cette fenêtre risque de sur-apprendre le biais directionnel du marché plutôt que la logique des principes.
- **GBPUSD uniquement** — aucune généralisation testée à d'autres paires.
- **`PRICE_LAG_AT_NODE_BIRTH` ≈ 90% des triggers** — risque de modèle dégénéré qui apprend simplement "PRICE_LAG déclenché ⇒ WIN" sans discriminer le contexte fin.
- **Sessions New York/After exclues** (`skipped.jsonl` séparé) — le modèle ne voit jamais ces contextes ; tout déploiement futur sur ces sessions serait hors distribution d'entraînement.
- **Labels dépendants de la stratégie DYNAMIC** (TP/SL par session, Brief O1) — un changement futur de stratégie de sortie invaliderait ces labels ; le dataset devrait être régénéré (le script est idempotent, cf. ci-dessous).

## Features

Contexte assemblé par `PrincipleEngine._load_shared_context()` (contrat `docs/architecture/CONTEXT_CONTRACT.md` Couche 7 — état ACTUEL, pas le chiffre "31 champs" historique de `docs/AGENT.md` 2026-07-06/07, obsolète depuis les ajouts Phase 13 risk_assessment/regime/zone_diagnostics/news-aware). Métadonnées (symbol, timeframe, session_marche, timestamp) séparées des features, marquées explicitement.

**Interdit et vérifié absent des features** : tout champ postérieur à la décision (`resolution_*`, MFE/MAE réalisés, `exit_reason`) — `_load_shared_context()` ne lit jamais la table `decisions`, aucune fuite possible par construction.

## Split

Chronologique STRICT (train 80% le plus ancien, val 10%, test 9% le plus récent). Aucun shuffle inter-périodes. 1 décision = 1 snapshot unique (vérifié Brief O1/O2 : 0 snapshot avec >1 décision `preparer_entree`) — aucun risque de répartir un même snapshot sur deux splits.

## Formats

- `{split}.jsonl` — classification brute `{"features": {...}, "label": 0|1, "pips": x}`.
- `{split}_chat.jsonl` — chat-template `{"messages":[{"role":"user","content":"<contexte JSON>"},{"role":"assistant","content":"WIN|LOSS"}]}` (cible qwen3-coder 4B / phi3 3.8B, quantization Q4_K_M — documentaire, rien à faire ici).
- `skipped.jsonl` — mêmes champs, décisions New York/After (analyse future).

## Entraînement

**NON ouvert.** Ce brief couvre uniquement la préparation du dataset + carte de données. Le fine-tuning est un GO séparé de Søn, à tracer dans DECISIONS_LOG AVANT implémentation (R17/R19). Le modèle éventuel reste HORS du cœur cognitif (R18) — outil d'analyse/shadow uniquement.

## Hachages MD5 + régénération

Voir `docs/reports/DATASET_V9_TRADER_MINI_MD5SUMS.txt`.
Régénération idempotente : `python scripts/v9_export_dataset.py --apply --output data/datasets/v9_trader_mini/` (dry-run par défaut sans `--apply`).
