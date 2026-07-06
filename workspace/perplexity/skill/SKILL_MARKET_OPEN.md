# Skill : Observation ouverture marché PowerFlow

## Référence horaire
- Ouverture : dimanche 23h Paris / 22h UTC
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