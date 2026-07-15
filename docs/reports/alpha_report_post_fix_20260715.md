# PowerFlow V9 — Rapport Alpha

*Généré le 2026-07-15T22:08:16.744254+00:00 (min_n=10)*

## Top principes (expectancy)

| # | Principe | Expectancy (pips) | n |
|---|---|---|---|
| 1 | PRICE_LAG_AT_NODE_BIRTH | +5.721 | 8092 |
| 2 | ZONE_RETEST | +1.813 | 246 |
| 3 | POWER_ANGLE_BREAK_TO_PRICE_IMPACT | +0.804 | 333 |
| 4 | GRAVITY_RESPRING_NODE | +0.465 | 131 |
| 5 | GRAMMAR_CONTEXTE_ADAPTIVE | -0.040 | 20 |
| 6 | PRICE_LAG_AT_NODE_BIRTH_ADAPTIVE | -0.257 | 14 |
| 7 | GRAMMAR_PULLBACK | -0.494 | 16 |
| 8 | GRAMMAR_PULLBACK_ADAPTIVE | -0.494 | 16 |
| 9 | GRAMMAR_CONTEXTE | -0.890 | 77 |
| 10 | NODE_BIRTH_FAST | -3.400 | 20 |

## Bottom principes (expectancy)

| Principe | Expectancy (pips) | n |
|---|---|---|
| GRAMMAR_PULLBACK | -0.494 | 16 |
| GRAMMAR_PULLBACK_ADAPTIVE | -0.494 | 16 |
| GRAMMAR_CONTEXTE | -0.890 | 77 |
| NODE_BIRTH_FAST | -3.400 | 20 |
| RAW_NODE_BIRTH | -3.400 | 20 |

## Anomalies — principes non rentables

| Principe | Expectancy | n | Action proposée |
|---|---|---|---|
| GRAMMAR_CONTEXTE_ADAPTIVE | -0.040 | 20 | ⚠️ surveiller / DORMANT |
| GRAMMAR_CONTEXTE | -0.890 | 77 | ⚠️ surveiller / DORMANT |
| NODE_BIRTH_FAST | -3.400 | 20 | ⚠️ surveiller / DORMANT |
| RAW_NODE_BIRTH | -3.400 | 20 | ⚠️ surveiller / DORMANT |

## Edge decay (dégradation d'edge)

- ⚠️ PRICE_LAG_AT_NODE_BIRTH: edge decay -18.9% sur 50 trades (récent 68.0% vs global 86.9%)

## Zones underperforming

| Principe | Dimension | Valeur | WR | Δ | n |
|---|---|---|---|---|---|
| PRICE_LAG_AT_NODE_BIRTH | session | after | 0.0% | -86.9 | 64 |
| PRICE_LAG_AT_NODE_BIRTH | session | london | 69.5% | -17.4 | 1775 |
| PRICE_LAG_AT_NODE_BIRTH | session | new_york | 0.0% | -86.9 | 145 |
| PRICE_LAG_AT_NODE_BIRTH | session | overlap | 61.5% | -25.4 | 148 |
| PRICE_LAG_AT_NODE_BIRTH | regime | RETOUR_EQUILIBRE | 53.9% | -33.0 | 26 |
| PRICE_LAG_AT_NODE_BIRTH | direction | baissiere | 67.5% | -19.4 | 1881 |
| ZONE_RETEST | session | after | 0.0% | -57.3 | 19 |
| ZONE_RETEST | session | new_york | 0.0% | -57.3 | 48 |
| POWER_ANGLE_BREAK_TO_PRICE_IMPACT | session | after | 0.0% | -54.4 | 21 |
| POWER_ANGLE_BREAK_TO_PRICE_IMPACT | session | new_york | 0.0% | -54.4 | 62 |
| GRAVITY_RESPRING_NODE | session | new_york | 0.0% | -51.9 | 24 |
| GRAMMAR_CONTEXTE | direction | baissiere | 29.7% | -32.6 | 37 |
| NODE_BIRTH_FAST | direction | baissiere | 16.7% | -18.3 | 12 |
| RAW_NODE_BIRTH | direction | haussiere | 16.7% | -18.3 | 12 |

## Cascades boosters

Aucune cascade booster découverte.

## Cascades dampeners (combinaisons à éviter)

| Cascade | WR | Lift | n |
|---|---|---|---|
| GRAVITY_RESPRING_NODE+PRICE_LAG_AT_NODE_BIRTH | 51.9% | -35.0 | 131 |
| GRAMMAR_CONTEXTE+PRICE_LAG_AT_NODE_BIRTH | 60.7% | -26.1 | 56 |
| NODE_BIRTH_FAST+POWER_ANGLE_BREAK_TO_PRICE_IMPACT | 35.0% | -19.4 | 20 |
| POWER_ANGLE_BREAK_TO_PRICE_IMPACT+RAW_NODE_BIRTH | 35.0% | -19.4 | 20 |
| POWER_ANGLE_BREAK_TO_PRICE_IMPACT+ZONE_RETEST | 47.6% | -9.7 | 170 |
| PRICE_LAG_AT_NODE_BIRTH+ZONE_RETEST | 78.7% | -8.2 | 75 |
| GRAMMAR_CONTEXTE+GRAMMAR_CONTEXTE_ADAPTIVE | 55.0% | -7.3 | 20 |

