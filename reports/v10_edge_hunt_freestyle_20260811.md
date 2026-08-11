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

## VERDICT NET FINAL — ACTIONNABLE (spread réel mesuré)
Spread réel en Overlap mesuré dans la DB : médiane 0.1-0.3 pip, 73-100% du temps < 0.7 pip.

PnL net avec le VRAI spread distribué par paire (ratio TP/SL symétrique 1xATR, hold 4) :
| Paire | n | WR | PnL net |
|---|---|---|---|
| EURUSD | 91 | 61.5% | +110.5 |
| USDCHF | 161 | 57.8% | +117.9 |
| AUDUSD | 158 | 56.3% | +55.7 |
| GBPUSD | 235 | 54.0% | +14.3 |
| USDJPY | 107 | 53.3% | -12.1 |
| USDCAD | 140 | 50.0% | -21.3 |
| **TOTAL** | **892** | **55.2%** | **+265.1** |

Filtre 3 paires porteuses (EURUSD+USDCHF+AUDUSD) : n=410, WR 58.1%, PnL +278.5, walk-forward 4/5.

**VERDICT : EDGE ACTIONNABLE.** PnL net > 0 avec spread réel sur 892 trades. Les paires
faibles (USDJPY, USDCAD) à exclure. R10 : passer en SHADOW paper sur EURUSD/USDCHF/AUDUSD
en Overlap avant tout micro-lot réel.

## R10 (inchangé)
- Spread réel mesuré : < 0.7 pip en Overlap sur 73-100% du temps → edge actionnable.
- MAIS zéro ordre réel : passer en SHADOW paper sur EURUSD/USDCHF/AUDUSD en Overlap,
  30 trades, avant tout micro-lot. Levier max = uniquement si edge + spread confirmés
  en temps réel live.

## Fichiers livrés (scripts/ , R2 additif)
- v10_edge_hunt_freestyle.py — scan brut
- v10_edge_hunt_freestyle2.py — scan magnitude + session
- v10_edge_walkforward.py — walk-forward simple 2 règles
- v10_edge_validate.py — walk-forward glissant + PnL TP/SL
- v10_edge_directional.py — test directionnel PUR (ratio symétrique)
- v10_edge_wf_final.py — walk-forward final 5 fenêtres
- v10_edge_spread_robustness.py — robustesse spread + horizon
