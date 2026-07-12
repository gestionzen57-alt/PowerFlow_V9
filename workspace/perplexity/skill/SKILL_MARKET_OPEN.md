# Skill : Observation ouverture marché PowerFlow

## Référence horaire
- Ouverture : dimanche 23h Paris — **21h UTC en heure d'été** (22h UTC en heure d'hiver,
  DST-aware via `America/New_York`/`zoneinfo`, cf. `core/v9/market_calendar.py`, commit
  `e42d81b` 2026-07-07). Ne JAMAIS supposer 22h UTC fixe toute l'année — corrigé au
  Brief R (2026-07-12), vérifier que les crons de résolution raisonnent en UTC vrai
  (horodatage `datetime.now(timezone.utc)`, jamais d'heure locale implicite).
- Broker Tickmill : GMT+3
- Tous timestamps doivent être en UTC pour comparaison

## Procédure
Suivre workspace/perplexity/assets/MARKET_OPEN_TEMPLATE.md

## À observer en priorité
- AUD : plausibilité ±15 unités entre EUR et NZD (détecte inversion SDI)
- zone_diagnostics : 9/27 principes en dégradation gracieuse = ATTENDU
- Latence chaîne cognitive : cible 200ms/couche, référence 189ms
- Stale data : STALEGATE doit bloquer si données trop anciennes

## Format de sortie
Mini-checkpoint post-open selon MARKET_OPEN_TEMPLATE.md