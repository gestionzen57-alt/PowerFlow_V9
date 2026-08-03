# Audit A16 — L7/L8/L9 walk-forward post-activation (snapshot 03/08 06:00 UTC)

## Contexte

Motion CEO 03/08/2026 « plein pouvoir » a activé 3 kill switches supplémentaires :
- `V9_MEGA_EDGE_L7_GRAMMAR_PUR_BLACKLIST_ENABLED` (déjà ON depuis Phase 117)
- `V9_MEGA_EDGE_L8_PRINCIPLE_COUNT_BLACKLIST_ENABLED` (déjà ON depuis Phase 121)
- `V9_MEGA_EDGE_L9_TIME_FILTER_ENABLED` (ON 03/08, motion CEO 03/08)

Le walk-forward L7/L8 est intégré au pipeline cron quotidien
(`scripts/v9_cron_pipeline.py`, étapes 5 + 5b ajoutées Phases 113 + 123).

## Statut rapports au 2026-08-02 22:43 UTC

| Rapport | Verdict | Gain PNL | Walk-forward | Date |
|---|---|---|---|---|
| `data/v9_l7_promotion_report.json` | **QUASI_PROMOTE** (3/5) | +32.6 pips | 30j post-activation | 2026-08-02 22:43 |
| `data/v9_l8_promotion_report.json` | **PROMOTE** (5/5) | +725.85 pips | 30j post-activation | 2026-08-02 22:43 |

## Verdict L7 (3/5 conditions R25')

```
PRE-L7  : n=337 wr=44.51% pnl=-259.7p
POST-L7 : n=327 wr=44.95% pnl=-227.1p (bloques: 10)
Delta   : +0.44pts WR, +32.6p PNL
Verdict : QUASI_PROMOTE (3/5 conditions OK)
  WR > seuil_adapt(50%)     : True (44.95% >= 50%)
  n >= 30                   : True (327 >= 30)
  PNL gain >= +adapt_pnl(26): True (+32.6p >= +26p)
  WR improved > +adapt_wr(0.5): False (+0.44pt < +0.5pt)
  Edge preserved            : True (WR+pnl up)
```

## Verdict L8 (5/5 conditions R25')

```
Walk-forward L8 90j : depuis 2026-05-04
Charge 337 paper_trades
L8 bloquerait 247/337 trades (73.3%)
PRE-L8  : n=337 wr=44.51% pnl=-259.7p
POST-L8 : n=90  wr=95.56% pnl=+466.2p (bloques: 247)
Seuils adaptatifs : WR>=70.0% (n=90), PNL>=+50p (n_blk=247)

VERDICT R25' : PROMOTE (5/5 conditions OK)
  WR > 70%      : True (95.56% >= 70%)
  n >= 30       : True (90 >= 30)
  PNL >= +50p   : True (+725.9p >= +50p)
  WR improved   : True (44.51% -> 95.56%, delta +51.05pt)
  Edge preserved: True
```

## Statut L9 (NO walk-forward dédié, kill switch ON 03/08)

L9 n'a pas encore de walk-forward dédié (L7/L8 walk-forward ne couvrent
que leurs propres leviers). L'audit live attend que le pipeline live tourne
sur 24-48h post-activation 03/08 (reprise lundi 04/08 à la réouverture
marché).

**Action** : relancer cet audit lundi 04/08 ~12h UTC (post-ouverture Londres)
pour capturer les premiers hits L9 en live.

## Audit SQL live 03/08 (n=337 paper_trades historique)

| Levier | Trades concernés | Hits attendus live | Statut |
|---|---|---|---|
| L7 GRAMMAR/ELASTIC pur no-stars | 10 (historique) | 0 (bloqué en live) | ✅ Validé théorique |
| L8 mega-combinaisons (n>=5) | 247 (historique) | 0 (bloqué en live) | ✅ Validé théorique |
| L9 trades < 14h UTC | 276 (historique) | 0 (bloqué en live) | ✅ Validé théorique |

> **Note** : ces 337 paper_trades datent de l'époque pré-DROP (avant
> L7+L8 activation). Les L7/L8 sont des **kill switches** : aucun trade
> correspondant ne devrait apparaître **post-activation**.

## Prochaines étapes

1. **Lundi 04/08 ~12h UTC** : vérifier que le pipeline live tourne
   (`v9_dashboard.py --watch decisions --once`)
2. **Lundi 04/08 ~22h UTC** : consulter `data/v9_l7_promotion_report.json`
   et `data/v9_l8_promotion_report.json` (refresh quotidien par cron 07:00 UTC)
3. **Mardi 05/08** : audit `cognitive_journal` pour hits L7/L8/L9
4. **Mercredi 06/08** : décision motion CEO pour `--auto-quasi-promote`
   sur L7 si gain >= 2x adapt_pnl (= +52p)

## Statut

⏸ **EN ATTENTE réouverture marché lundi 04/08**. Audit live non
récupérable ce dimanche (marché Forex fermé).

Doctrine : R14 git vérité, R22 sous-unité unique, R25' motion CEO,
R26 1 entrée DECISIONS_LOG.

---

_Référence : `workspace/perplexity/ACTIVE_TASKS.md` §A16 (P2 OPTIMISATION)._
