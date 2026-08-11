# EDGE HUNT FREESTYLE — Résultat final (11/08/2026)

Mode freestyle (mandat CEO plein pouvoir, rien à perdre). Objectif : trouver
un signal réellement prédictif de la direction future, SANS lookahead.

## Méthode
- Scan agressif de features brutes (forces, momentum, volume, spread, session)
- Validation rigoureuse : walk-forward glissant + PnL réel TP/SL ATR + ratio symétrique
- 100% point-in-time (features calculées à barre t, cible = barres futures)

## Résultat brut du scan (toutes features, 17k obs)
- sign_forces, mom_forces, vol_up, spread_hi, cmom, dir_col : TOUS ≈ 50% (bruit)
- La simple direction des forces ne prédit RIEN.

## EDGE TROUVÉ : déséquilibre FORT × session Overlap
`OVERLAP session + |delta_forces| >= 15` (magnitude, pas juste le signe)

| Test | Résultat | Verdict |
|---|---|---|
| Walk-forward 5 fenêtres | 5/5 ≥51%, PnL +1048 pips | ✅ stable |
| Ratio TP/SL symétrique 1.0 | WR 54.2%, PnL +1048 pips | ✅ edge réel |
| Ratio TP/SL 0.5 | WR 58.0% | ✅ |
| Par paire (6 paires) | 6/6 PnL positif | ✅ robuste |
| Robustesse spread 0.5 pip | WR 53.9%, PnL +232 | 🔶 survivable |
| Robustesse spread 1.0 pip | WR 53.1%, PnL -629 | 🔴 meurt |
| Horizon hold 2/4/6 | PnL +660/+1094/+1210 | ✅ croissant |

## Verdict clairvoyant
- **Edge RÉEL et STABLE** sur le plan directionnel : OVERLAP + delta_forces≥15
  donne WR 54% à ratio symétrique, 5/5 fenêtres, 6/6 paires. Ce N'EST PAS du bruit.
- **MAIS fragile au spread** : rentable < ~1 pip, perdant à 1 pip+.
- Exploitable UNIQUEMENT si spread réel serré (< 0.7 pip) pendant Overlap.
- L'edge vient de la MAGNITUDE du déséquilibre de forces en session Overlap,
  pas du simple signe — c'est une vraie découverte vs le système Fatman actuel.

## R10 (inchangé)
- Aucun ordre réel tant que le spread réel n'est pas mesuré < 0.7 pip sur la paire.
- À valider en SHADOW live (paper) avant tout micro-lot. Levier max = uniquement
  si edge + spread + fraîcheur confirmés en temps réel.

## Fichiers livrés (scripts/ , R2 additif)
- v10_edge_hunt_freestyle.py — scan brut
- v10_edge_hunt_freestyle2.py — scan magnitude + session
- v10_edge_walkforward.py — walk-forward simple 2 règles
- v10_edge_validate.py — walk-forward glissant + PnL TP/SL
- v10_edge_directional.py — test directionnel PUR (ratio symétrique)
- v10_edge_wf_final.py — walk-forward final 5 fenêtres
- v10_edge_spread_robustness.py — robustesse spread + horizon
