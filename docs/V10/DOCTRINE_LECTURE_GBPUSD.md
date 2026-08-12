# DOCTRINE DE LECTURE GBPUSD — Hermes (2026-08-12)

> **La lecture du marché n'est pas une suite de valeurs : c'est une COURBE.**
> Chaque indicateur (Fatman, VSA, prix) a une cinématique — des pics, des
> creux, des pentes, des divergences. C'est cette cinématique qui révèle les
> retournements AVANT qu'ils n'arrivent.

## PRINCIPE 1 — LA COURBE AVANT LA VALEUR
- Une valeur isolée (GBP=76) ne dit rien. La COURBE dit tout.
- Regarder : pic → retombée (exhaustion), divergence force/prix, accélération.
- Un pic de force suivi d'une retombée pendant que le prix pousse = piège.

## PRINCIPE 2 — LA DIVERGENCE EST LE SIGNAL
- Force GBP monte en pic, puis décline, MAIS le prix fait un nouveau sommet
  non confirmé → le prix ment → retournement vendeur probable.
- La force ne suit pas le prix au sommet = les acheteurs s'épuisent.

## PRINCIPE 3 — LE SWEEP PRÉCÈDE LE RETOURNEMENT
- Le prix balaie un niveau de liquidité (high/low) pour prendre les stops
  PUIS se referme en dessous/au-dessus = stop hunt → retournement.
- Le sweep de buy-side liquidity (au-dessus d'un high) précède une baisse.

## PRINCIPE 4 — LA CONFLUENCE FAIT LE SIGNAL FORT
- Un seul facteur (ex: force extrême) = bruit (32% fiable).
- Plusieurs facteurs alignés = signal fort :
  EXHAUSTION + DIVERGENCE + SWEEP + REJET = STRONG.
- Score >= 5 = STRONG (alerte), >= 3 = MODERATE, sinon WEAK.

## PRINCIPE 5 — L'ANTICIPATION AVANT LA RÉACTION
- On détecte le retournement AVANT qu'il n'arrive (pic en épuisement,
  divergence, sweep), pas après (prix déjà retombé).
- Le point de vente optimal est au pic, pas après la chute.

## PRINCIPE 6 — LA CONFIRMATION AVANT L'ACTION
- Le signal ANTICIPÉ n'est pas un ordre. Confirmer par :
  - un rejet (close sous le niveau après l'avoir touché)
  - un SL au-dessus du sommet
- R10 : zéro ordre réel tant que la confirmation n'est pas là.

## PRINCIPE 7 — L'APPRENTISSAGE QUOTIDIEN
- Chaque jour est unique. Ré-évaluer l'edge contre les données du jour.
- Journal d'apprentissage quotidien (v10_daily_learning.py).
- Ce qui a marché hier ne marchera pas forcément demain → ré-évaluer.

## OUTILS (scripts/)
- v10_force_cinematics.py : lecture en courbe (pics, creux, divergence, exhaustion)
- v10_liquidity_sweep.py : détection de sweep (stop hunt)
- v10_level_reader_gbp.py : niveaux (résistances/supports)
- v10_market_reader_gbp.py : Fatman + VSA + MTF
- v10_gbpusd_master_alert.py : alerte unifiée (toutes lectures combinées)
- v10_daily_learning.py : apprentissage quotidien

## SKILLS
- powerflow-v10-no-limit-edge-engine : la doctrine du plein potentiel
- powerflow-v10-autopilot-loop : playbook NO-LIMIT

## MÉTRIQUE DE RÉUSSITE
- Le système doit détecter le retournement AVANT la chute (anticipation).
- Taux de bonnes décisions > 55% en lecture anticipative.
- PnL net positif en simulation (si edge validé).
