# Axe 2 — Calibration Phase E : contaminée par la catastrophe ? (NON)

> **Audit edgefund V9 — Axe 2/8** · OPUS Claude Code · 2026-07-19 · lecture seule.

## Question (prompt)

Le `v9_bayesian_predictor.py` a-t-il été fit **avant** ou **après** le fix boucle
`c0aa416` ? Si le fit inclut les 4751 trades catastrophiques du 17/07, la calibration
est biaisée et doit être re-fittée.

## Réponse : la calibration N'EST PAS contaminée

Deux faits vérifiables (R14) :

### 1. Ordre chronologique des commits

```
bf93150  2026-07-18 15:09:27  feat: Phase E — 5 modules core (dont bayesian_predictor)
c0aa416  2026-07-18 15:59:30  fix: kill PRICE_LAG boucle 17/07
```

→ Le fit est **antérieur** de 50 min au fix. **Mais cet ordre est sans conséquence** (point 2).

### 2. Le fit lit `decisions`, PAS `paper_trades`

`scripts/v9_bayesian_fit.py` → `fit_from_decisions_db()` :

```sql
SELECT ..., d.is_win, d.resolution_pips
FROM decisions d
WHERE d.is_win IS NOT NULL
```

- La calibration est fittée sur la table **`decisions`** (dédupliquée, 1 ligne/signal,
  labellisée par le **résolveur**).
- Les **4751 trades catastrophiques vivent dans `paper_trades`** (table du trader live),
  **jamais** dans `decisions`. Ils n'ont donc **jamais** fait partie du fit.
- Le fix `c0aa416` modifie le **garde PRICE_LAG du trader live** — il ne réécrit
  aucune ligne de `decisions`. Un re-fit post-`c0aa416` consommerait exactement les
  mêmes lignes → **résultat identique**. Le re-fit demandé par le prompt est un **no-op**.

## Le vrai caveat (déjà connu) : in-sample / data-snooping

La calibration reste fittée sur des **labels résolveur in-sample** (rejoués sur la fenêtre
d'entraînement). BSS = 0,022 est un uplift **faible et fragile** — non parce qu'il est
contaminé par la boucle, mais parce qu'il n'est pas validé **out-of-sample**. Voir le
walk-forward `learn_loop_v1` (std ≈ 45 pts sur les folds agressifs → verdict NO-GO Phase F).

## Recommandation

1. **Pas de re-fit d'urgence** — la contamination supposée est réfutée.
2. **Toute promotion GO doit s'appuyer sur du walk-forward out-of-sample**, jamais sur
   le BSS in-sample ni sur les pips résolveur (cf Axe 1 §5).
3. Documenter dans le predictor un `provenance` explicite : « fit sur `decisions`
   (labels résolveur in-sample), NON représentatif du live tant que non walk-forward validé ».

## Score Axe 2

| Critère | Cible | Résultat |
|---|---|---|
| Ordre commits vérifié | — | ✅ fit avant fix, mais sans effet (source = `decisions`) |
| Contamination | re-fit si biaisé | ❌ **pas de contamination** — re-fit no-op |
| Caveat identifié | BSS ≥ +0,05 | in-sample fragile, exiger walk-forward (renvoi Axe 8) |
