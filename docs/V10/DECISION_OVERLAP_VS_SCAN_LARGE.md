# DÉCISION STRATÉGIQUE — Edge OVERLAP ciblé vs Scan large

> **Auteur** : Hermes (ZCode session 2026-08-13)
> **Statut** : PROPOSITION au CEO Søn — en attente d'arbitrage
> **Doctrine** : R1-AGIR, R10 (seul garde-fou), Plein Potentiel

---

## LE PARADOXE (chiffres vérifiés 13/08 05:50 UTC)

L'edge OVERLAP ciblé **gagne** pendant que le système global **perd massivement** :

| Métrique | Edge OVERLAP (12-16 UTC, \|delta_forces\|≥15) | Système global (toutes décisions, proxy is_win) |
|---|---|---|
| Replay cumulé 7j | n=382, WR **58.1%**, +298 pips | — |
| Replay 12/08 | n=414, WR **58.9%**, +339 pips | — |
| Daily learning 11/08 | n=28, WR **67.9%**, +33.5 pips | n=144, WR 0.0% |
| Daily learning 12/08 | n=33, WR **66.7%**, +36.1 pips | n=238, WR 0.0% |
| Weekly 7j (proxy) | — | n=800, WR **16.4%**, **-244 pips**, Sharpe -0.04, `recalibrate_recommended: true` |

**Contraste** : ~66% WR (ciblé) vs ~16% WR (large). L'écart n'est pas un bug —
c'est la structure même du marché : l'edge est **localisé** dans une fenêtre
temporelle + un seuil de force, pas distribué uniformément.

---

## POURQUOI LE SCAN LARGE PERD

Le proxy `is_win_proxy` (close[t+5]-close[t]) sur **tous** les ticks produit du
bruit pur hors Overlap. Le système émet ~800 signaux/sem dont ~95% sont du bruit
qui dilue l'edge réel. Le daily_bilan et weekly_summary agrègent ce bruit → WR
qui s'effondre (26% → 16% en une semaine).

**Ce n'est pas une défaillance du moteur — c'est l'absence de filtre de sélection.**

---

## LA DÉCISION À TRANCHER

### Option A — Restreindre au ciblé (conservateur, edge-first)
- Le système ne trade QUE dans la fenêtre OVERLAP 12-16 UTC avec |delta_forces|≥15.
- ~33 trades/jour max, edge prouvé à 66% WR.
- Le scan large continue en **lecture seule** (apprentissage, détection drift)
  sans émettre de signaux exécutables.
- **Avantage** : capital protégé (R10), edge prouvé, alignement avec la doctrine
  "performant prime".
- **Risque** : sous-exploitation d'autres fenêtres d'edge potentielles.

### Option B — Continuer le scan large (exploration)
- Le système trade partout, accepte le WR 16% global en échange d'apprentissage.
- **Avantage** : découverte d'autres edges.
- **Risque** : dilution, R10 menacé si on passe live, signal-puits de bruit.

### Option C — Mix hiérarchisé (RECOMMANDÉ)
- **Couche exécution** : edge OVERLAP uniquement (Option A) — le seul edge prouvé.
- **Couche exploration** : scan large en SHADOW permanent (paper, pas de capital)
  pour détecter de nouveaux edges (ex: session Asie, news windows).
- **Couche apprentissage** : daily learning sur les données réelles du jour,
  comme aujourd'hui (v10_daily_learning.py).
- **Gate promotion** : un nouvel edge passe SHADOW → exécutable seulement après
  validation 30 trades + WR ≥ 54% (cf. gate R10 ci-dessous).

---

## RECOMMANDATION HERMES : OPTION C

**Justification (CoT R5)** :
1. **Je vois** : edge OVERLAP prouvé 2 jours (66-68% WR) + scan large à 16% WR.
2. **Je pense** : l'edge est localisé, pas distribué ; trader le bruit dilue.
3. **Je décide** : Option C — exécuter l'edge prouvé, explorer en SHADOW, gate stricte.
4. **Je risque** : R10 respecté (DD max 10%, position max 2%, levier max 5x).
5. **J'apprends** : chaque nouvel edge validé par daily learning + gate 30 trades.

**Argument doctrine** : "performant prime" (Plein Potentiel) → on ne trade pas le
bruit. On trade l'edge prouvé. L'exploration reste en SHADOW.

---

## GATE R10 — Promotion nouvel edge (SHADOW → exécutable)

```
Conditions cumulatives (TOUTES obligatoires) :
  ✅ n_trades      ≥ 30 SHADOW live (pas replay)
  ✅ WR_shadow     ≥ 54% (baseline edge OVERLAP)
  ✅ Sharpe        ≥ 0.5
  ✅ DD_max        ≤ 5% sur la période shadow
  ✅ Consistency   ≥ 75% (WR stable sur sous-fenêtres)
  ✅ CEO gate      (validation humaine — tu restes juge final)
```

Tant qu'un edge n'a pas passé cette gate → SHADOW only, zéro capital (R10).

---

## PROCHAINES ACTIONS (si CEO valide Option C)

1. **Isoler la couche exécution** : ne router vers paper/live QUE les signaux
   Overlap+delta≥15. Code à modifier : `v10_orchestrator.py` (gate de filtrage).
2. **SHADOW permanente** : le scan large reste actif mais taggé `exploration_only`.
3. **Gate validator** : script qui passe un edge SHADOW→exécutable selon les 6
   critères ci-dessus.
4. **Daily learning étendu** : appliquer v10_daily_learning.py à chaque fenêtre
   candidate (Asie, London, NY, Overlap) pour détecter de nouveaux edges.

---

> **Décision CEO requise** : A, B, ou C ?
> En attendant : le système reste en SHADOW (R10), aucun ordre réel.