# Audit Phase E — Migration `principle_scores.strategy` : CHANTIER FERMÉ (prémisse fausse)

**Date** : 2026-07-21
**Provider** : Claude Opus 4.8 (Claude Code CLI, mode AUTO-PILOTE nuit)
**Branche** : `feat/v9-resolve-drift-loop-20260720` (HEAD d172fc0)
**Motion source** : brief `PROMPT OPUS — Migration principle_scores.strategy Phase E`
**Verdict** : ❌ **NO-GO migration** — la prémisse du brief est factuellement fausse à **3 niveaux indépendants**. Aucune migration livrée (fabrication interdite par le brief lui-même). Chantier fermé proprement, escalade CEO.

---

## TL;DR

Le brief demande d'ajouter une colonne `strategy` à `principle_scores` pour que le méta-optimizer « diverge » et sorte du verdict `RED_NO_UPLIFT`. **Cette colonne ne servirait à rien** :

1. **Le méta-optimizer ne lit aucune colonne `strategy`.** Ses filtres SQL sont des **expressions `win_rate`/PF** sur les colonnes existantes, pas un `WHERE strategy = ...`.
2. **Les stratégies divergent déjà** dans le scoring des candidats (TRAILING WR agrégé 87.6 / PF 51 vs TP_SL 71.5 / 9.4). Ce n'est **pas** `no_candidates_db_empty`.
3. **Le verdict `RED_NO_UPLIFT` est structurel**, garanti mathématiquement par la simulation elle-même (mêmes `pips` assignés à legacy ET meta), indépendamment de tout contenu DB.

Bonus : **`paper_trades` ne contient aucune donnée source** (`resolution_strategy`, `tp_pips`, `sl_pips`, `duration` absents) — la migration serait de toute façon impossible sans **inventer** la distribution, ce que le brief interdit explicitement (anti-pattern §« ❌ Inventer une distribution »).

---

## Preuves factuelles

### Fait 1 — Schéma réel ≠ schéma supposé par le brief

Brief supposait : `paper_trades` contient `tp_pips_recommended`, `sl_pips_recommended`, `resolution_strategy`, `resolution_details`.

Schéma **live** (`PRAGMA table_info`) :

```
paper_trades     : trade_id, snapshot_id, direction, confiance, principes_source,
                   opened_at, closed_at, pips_simulated, is_win, risk_go_context
principle_scores : id, principle_id, combination_hash, n_trades, n_wins, n_losses,
                   total_pips, avg_pips, win_rate, last_updated
```

- Aucune colonne TP/SL/durée/strategy dans `paper_trades`.
- `risk_go_context` = JSON minimal `{"news_phase": "...", "window_status": "..."}` — pas de TP/SL.
- Volumétrie réelle : `paper_trades` = **193 lignes** (192 clôturées), pas 4817/4995. `principle_scores` = **347 lignes**.

→ **Aucune source pour peupler `strategy`.** Même chemin d'erreur que Motion #32 (schéma fantôme).

### Fait 2 — Le méta-optimizer ne query pas de colonne `strategy`

`core/v9/v9_meta_strategy_optimizer.py` L290-305, le SQL réel par candidat :

```sql
SELECT SUM(n_trades), SUM(n_wins), SUM(n_losses), SUM(total_pips),
       AVG(NULLIF(win_rate,0)), SUM(total_pips)/MAX(1,SUM(n_losses))
FROM principle_scores
WHERE 1=1 {extra_filter}
```

Où `{extra_filter}` (L246-251) est une **expression WR/PF**, jamais `strategy` :

```
TP_SL      : ""                                                     (tous)
TRAILING   : " AND win_rate > 0.70 AND (total_pips/MAX(1,n_losses)) > 2.0 "
TP_PARTIAL : " AND win_rate BETWEEN 0.50 AND 0.85 AND ... BETWEEN 1.0 AND 2.5 "
FAST_EXIT  : " AND n_trades > 0 AND avg_pips > -2.0 "
```

`grep strategy` sur le module → aucune référence à une colonne `strategy` dans le SQL. Ajouter la colonne = **no-op total** sur le comportement.

### Fait 3 — Les stratégies divergent DÉJÀ (pas `db_empty`)

Exécution des filtres réels sur la DB live :

| Stratégie   | n_trades | avg_wr | pf    |
|-------------|----------|--------|-------|
| TP_SL       | 13886    | 71.48  | 9.44  |
| TRAILING    | 8293     | 87.58  | 51.08 |
| TP_PARTIAL  | **0**    | 0.00   | 0.00  |
| FAST_EXIT   | 13562    | 77.01  | 10.49 |

- TRAILING obtient un scoring **très supérieur** à TP_SL → le méta **choisit déjà** des stratégies divergentes.
- Bug secondaire (hors périmètre, ne pas corriger) : `win_rate` est stocké **échelle 0-100** alors que les filtres comparent à `0.70`/`0.50`. Donc `> 0.70` matche tout, et `BETWEEN 0.50 AND 0.85` (TP_PARTIAL) ne matche rien → TP_PARTIAL toujours vide. Une colonne `strategy` ne corrige pas ce mismatch d'échelle.

### Fait 4 — `RED_NO_UPLIFT` est structurel (la vraie cause)

`scripts/v9_meta_strategy_simulation.py` L250-252 :

```python
pips = float(dec.get("pips") or 0.0)
legacy_results.append((legacy.recommended_strategy, pips))
meta_results.append((meta_strategy, pips))   # <-- MÊME pips
```

WR/PF (`_wr_pf`, L258-267) sont calculés **uniquement** à partir de `pips`. Les deux listes contiennent des `pips` **identiques** (l'outcome historique figé), quelle que soit la stratégie choisie par le méta.

→ **ΔWR ≡ 0 et ΔPF ≡ 0 par construction.** `RED_NO_UPLIFT` est mathématiquement garanti, indépendamment de la DB.

Exécution factuelle (5000 décisions, `--force-meta`, lecture seule) :

```
WR legacy : 80.70%   WR meta : 80.70%   ΔWR : +0.00 pts
PF legacy : 6.57     PF meta : 6.57     ΔPF : +0.00
Verdict   : RED_NO_UPLIFT
```

Le méta **diverge** en sélection de stratégie (Fait 3), mais la simulation **ne peut pas mesurer** l'effet d'un TP/SL différent : elle réutilise les `pips` historiques figés au lieu de re-simuler la trajectoire de prix sous le nouveau TP/SL.

---

## Le vrai goulot d'étranglement Phase E

Ce n'est **pas** une colonne manquante. C'est que **la simulation d'edge uplift est structurellement incapable de mesurer un uplift** : elle applique le même outcome (`pips` figé) aux deux bras. Pour mesurer l'effet d'un TP/SL méta différent, il faudrait :

- Soit rejouer la **trajectoire intrabar** (OHLC / ticks) de chaque décision et re-résoudre TP/SL sous la stratégie méta (nécessite les bougies post-entrée, pas juste `resolution_pips`).
- Soit un backtest event-driven séparé re-pricant chaque trade sous chaque stratégie candidate.

Les deux dépassent le périmètre du brief et **modifieraient** la simulation (le brief interdit de toucher le méta-optimizer, mais la simulation est le maillon à revoir — décision CEO requise).

---

## Décision

- ❌ **Migration NON livrée.** Elle serait un no-op (Fait 2), sans source de données (Fait 1), et nécessiterait de fabriquer une distribution — interdit par le brief (§ anti-pattern « ❌ Inventer une distribution de strategies si paper_trades n'a pas la donnée — clore le chantier proprement »).
- ✅ **Chantier fermé proprement**, conformément au critère de succès du brief : « OU chantier fermé proprement avec motion CEO documentée si la donnée est insuffisante ».
- ✅ **Aucune modification runtime, aucun schéma touché, aucune donnée fabriquée.** DB intacte (lecture seule intégrale). R2/R8/R18/R25' respectés par non-action.

## Escalade CEO (motions distinctes requises)

1. **Motion A — Re-scoper Phase E** : la mesure d'edge uplift exige une re-simulation intrabar (OHLC post-entrée) ou un backtest event-driven re-pricant sous chaque stratégie. Sans cela, `RED_NO_UPLIFT` restera structurel quoi qu'on migre.
2. **Motion B — Bug échelle `win_rate`** (optionnel, hors périmètre ici) : filtres méta comparent `win_rate` (stocké 0-100) à des seuils 0-1 → TP_PARTIAL toujours vide, seuils TRAILING/FAST_EXIT sans effet discriminant réel. À corriger côté optimizer si Phase E est re-scopée.

---

*Audit lecture seule. 0 écriture DB, 0 fabrication. Verdict honnête > uplift fabriqué.*
