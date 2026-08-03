# L15 Heatmap — regime × session × pattern (Phase 126)

**Généré le** : 2026-08-03T06:06:50.505446+00:00
**Total trades analysés** : 337
**Niches détectées (WR>70% ET n>=10)** : 4
**Kill switches proposés** : 4

## Top 10 niches structurelles

| Regime | Session | Pattern | n | WR | PNL | avg/trade |
|---|---|---|---|---|---|---|
| UNKNOWN | london | 1 | 31 | 100.0% | +179.5p | +5.79p |
| UNKNOWN | overlap | 1 | 22 | 100.0% | +99.0p | +4.5p |
| UNKNOWN | overlap | 2 | 14 | 92.9% | +86.0p | +6.14p |
| UNKNOWN | london | 2 | 11 | 100.0% | +54.5p | +4.95p |

## Heatmap 3D (regime × session × pattern)

Format : `[regime,session,pattern] : n=X WR=Y% PNL=Z p`

### Regime: CASSURE

- **asie**
  - pattern=5+: n=1 WR=0.0% PNL=-1.7p

### Regime: EXTENSION

- **asie**
  - pattern=5+: n=9 WR=0.0% PNL=-35.6p
- **london**
  - pattern=5+: n=4 WR=0.0% PNL=-24.3p
- **new_york**
  - pattern=5+: n=3 WR=0.0% PNL=-12.3p
- **overlap**
  - pattern=5+: n=1 WR=0.0% PNL=-3.9p

### Regime: NEUTRE

- **asie**
  - pattern=4: n=3 WR=66.7% PNL=+6.4p
  - pattern=5+: n=75 WR=28.0% PNL=-140.4p 💀
- **london**
  - pattern=5+: n=70 WR=10.0% PNL=-325.8p 💀
- **new_york**
  - pattern=5+: n=25 WR=52.0% PNL=-10.8p
- **overlap**
  - pattern=4: n=1 WR=100.0% PNL=+2.0p
  - pattern=5+: n=36 WR=44.4% PNL=-122.8p

### Regime: PALIER

- **asie**
  - pattern=5+: n=3 WR=0.0% PNL=-11.7p
- **new_york**
  - pattern=5+: n=1 WR=0.0% PNL=-0.9p

### Regime: REJET

- **london**
  - pattern=5+: n=1 WR=100.0% PNL=+3.0p

### Regime: RETOUR_EQUILIBRE

- **asie**
  - pattern=3: n=1 WR=0.0% PNL=-5.8p
  - pattern=4: n=1 WR=0.0% PNL=-3.4p
  - pattern=5+: n=7 WR=28.6% PNL=-11.4p
- **london**
  - pattern=5+: n=5 WR=20.0% PNL=-26.0p
- **new_york**
  - pattern=5+: n=2 WR=100.0% PNL=+19.0p
- **overlap**
  - pattern=5+: n=3 WR=0.0% PNL=-22.8p

### Regime: UNKNOWN

- **london**
  - pattern=1: n=31 WR=100.0% PNL=+179.5p 🔥
  - pattern=2: n=11 WR=100.0% PNL=+54.5p 🔥
- **overlap**
  - pattern=1: n=22 WR=100.0% PNL=+99.0p 🔥
  - pattern=2: n=14 WR=92.9% PNL=+86.0p 🔥
  - pattern=3: n=6 WR=100.0% PNL=+48.0p
  - pattern=5+: n=1 WR=100.0% PNL=+2.5p

## Heatmap 2D (symbol × session)

| Symbol | Session | n | WR | PNL |
|---|---|---|---|---|
| AUDUSD | asie | 24 | 41.7% | -6.4p |
| AUDUSD | london | 12 | 33.3% | -33.5p |
| AUDUSD | new_york | 10 | 60.0% | -2.5p |
| AUDUSD | overlap | 10 | 50.0% | -26.4p |
| EURUSD | asie | 19 | 42.1% | -17.2p |
| EURUSD | london | 15 | 13.3% | -61.6p |
| EURUSD | new_york | 4 | 25.0% | -13.2p |
| EURUSD | overlap | 5 | 0.0% | -45.3p |
| GBPUSD | asie | 26 | 23.1% | -48.4p |
| GBPUSD | london | 74 | 58.1% | +24.1p |
| GBPUSD | new_york | 4 | 100.0% | +22.5p |
| GBPUSD | overlap | 60 | 86.7% | +204.8p |
| USDCAD | asie | 4 | 0.0% | -18.5p |
| USDCAD | new_york | 3 | 0.0% | -12.4p |
| USDCAD | overlap | 3 | 0.0% | -31.0p |
| USDCHF | asie | 26 | 0.0% | -120.8p |
| USDCHF | london | 20 | 10.0% | -65.3p |
| USDCHF | new_york | 5 | 40.0% | -6.0p |
| USDCHF | overlap | 6 | 33.3% | -14.2p |
| USDJPY | asie | 1 | 100.0% | +7.7p |
| USDJPY | london | 1 | 0.0% | -2.8p |
| USDJPY | new_york | 5 | 40.0% | +6.6p |

## Kill switches proposés

### BOOST — `V9_HEATMAP_L15_BOOST_UNKNOWN_london_1_ENABLED`
- **Regime** : UNKNOWN
- **Session** : london
- **Pattern** : 1
- **Rationale** : WR=100.0% sur n=31 (top niche), gain 179.5p
- **Default** : 0 (R25' strict, motion CEO explicite)
- **Sizing multiplier** : 1.3

### BOOST — `V9_HEATMAP_L15_BOOST_UNKNOWN_overlap_1_ENABLED`
- **Regime** : UNKNOWN
- **Session** : overlap
- **Pattern** : 1
- **Rationale** : WR=100.0% sur n=22 (top niche), gain 99.0p
- **Default** : 0 (R25' strict, motion CEO explicite)
- **Sizing multiplier** : 1.3

### BLACKLIST — `V9_HEATMAP_L15_BLACKLIST_NEUTRE_asie_5+_ENABLED`
- **Regime** : NEUTRE
- **Session** : asie
- **Pattern** : 5+
- **Rationale** : WR=28.0% < 30% sur n=75 (anti-niche), perte -140.4p
- **Default** : 0 (R25' strict, motion CEO explicite)
- **Sizing multiplier** : 0.0

### BLACKLIST — `V9_HEATMAP_L15_BLACKLIST_NEUTRE_london_5+_ENABLED`
- **Regime** : NEUTRE
- **Session** : london
- **Pattern** : 5+
- **Rationale** : WR=10.0% < 30% sur n=70 (anti-niche), perte -325.75000000000017p
- **Default** : 0 (R25' strict, motion CEO explicite)
- **Sizing multiplier** : 0.0

## Doctrine

- R2 additif : heatmap + propositions, 0 modif code core/ (lecture seule)
- R6 fail-open : kill switches défauts OFF
- R14 git verite : chiffres extraits du SQL réel, pas inventes
- R22 sous-unite unique : 1 livrable = 1 heatmap
- R25' motion CEO explicite requise pour activation
- R26 DECISIONS_LOG entry dediee
- R28 Hermes operateur git unique