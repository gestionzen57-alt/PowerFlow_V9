---
name: powerflow-v9-news-heat-map
description: Use when working on Phase 143 L20 News Heat Map (modulation sizing par (symbol, news_type, minutes_to_news)).
---

# powerflow-v9-news-heat-map — Phase 143 L20

Module additif (R2) qui module le sizing selon la chaleur de la reaction
historique d'une paire (5 majeures) à un type de news (4 majeurs),
composee avec la fenêtre news (minutes_to_news) du L19 attenuator.

## Composition

`final_multiplier = MIN(base_multiplier, minutes_factor)`

Le **plus restrictif gagne** : si la heat map ecrase une paire (×0.0)
OU si la fenetre est en imminent (×0.0), le resultat est 0.0 (HALT).

## Audit SQL live 03/08 (R14, n=337 60j, jointure paper_trades ↔ forces_snapshots)

| Symbol | n | WR | avg pips | Politique heat map |
|---|---|---|---|---|
| **USDCHF** | 57 | 10.5% | -5.92 | Blacklist (×0.0) NFP/CPI/FOMC |
| **USDCAD** | 10 | 0.0% | -9.38 | Blacklist (×0.0) NFP/CPI/FOMC |
| **EURUSD** | 43 | 16.3% | -4.69 | ×0.2-0.3, ×0.1 sur ECB (choc direct) |
| **AUDUSD** | 56 | 28.6% | -3.53 | ×0.3-0.5 (fragile) |
| **USDJPY** | 7 | 42.9% | -0.16 | ×0.4-0.6 (sensible FOMC) |
| **GBPUSD** | 164 | 63.4% | -0.26 | ×0.5-0.7 (le plus resilient) |
| **XAUUSD** | 0 | n/a | n/a | Fallback ×0.5-0.7 (proxy conservateur) |

## Heat map (28 cellules)

```python
HEAT_MAP = {
    # USDCHF - le pire, blacklist sur news US directes
    ("USDCHF", "NFP"):  0.0, ("USDCHF", "CPI"):  0.0,
    ("USDCHF", "FOMC"): 0.0, ("USDCHF", "ECB"):  0.5,
    # USDCAD - blacklist historique (cf. v9_risk_parity)
    ("USDCAD", "NFP"):  0.0, ("USDCAD", "CPI"):  0.0,
    ("USDCAD", "FOMC"): 0.0, ("USDCAD", "ECB"):  0.5,
    # EURUSD - fragile, ECB = choc direct
    ("EURUSD", "NFP"):  0.2, ("EURUSD", "CPI"):  0.3,
    ("EURUSD", "FOMC"): 0.3, ("EURUSD", "ECB"):  0.1,
    # AUDUSD - fragile, sensible aux news US
    ("AUDUSD", "NFP"):  0.3, ("AUDUSD", "CPI"):  0.4,
    ("AUDUSD", "FOMC"): 0.3, ("AUDUSD", "ECB"):  0.5,
    # USDJPY - safe overall, sensible au FOMC
    ("USDJPY", "NFP"):  0.5, ("USDJPY", "CPI"):  0.5,
    ("USDJPY", "FOMC"): 0.4, ("USDJPY", "ECB"):  0.6,
    # GBPUSD - la plus resiliente historiquement
    ("GBPUSD", "NFP"):  0.6, ("GBPUSD", "CPI"):  0.7,
    ("GBPUSD", "FOMC"): 0.5, ("GBPUSD", "ECB"):  0.7,
    # XAUUSD - pas de data live, proxy conservateur
    ("XAUUSD", "NFP"):  0.7, ("XAUUSD", "CPI"):  0.5,
    ("XAUUSD", "FOMC"): 0.6, ("XAUUSD", "ECB"):  0.7,
}
DEFAULT_BASE_MULTIPLIER = 0.8  # fallback safe
```

## API

```python
from core.v9.v9_news_heat_map import (
    compute_news_heat_multiplier,
    classify_news_heat,
    news_heat_map_enabled,
    get_heat_map_snapshot,
    summarize_heat_verdicts,
    NewsHeatVerdict,
)
```

### `compute_news_heat_multiplier(symbol, news_type, minutes_to_news) -> float`

- Kill switch OFF → 1.0 (pass-through R25')
- Entree invalide (None, str non-num) → 1.0 (R6 fail-open)
- Symbol inconnu OU news_type invalide → fallback ×0.8
- Sinon → MIN(base, minutes_factor), clamp [0.0, 1.0]

## Kill switch

- Variable env : `V9_NEWS_HEAT_MAP_ENABLED`
- Défaut : `0` (R25' strict motion CEO)
- Activation : motion CEO explicite

## Doctrine

- **R2 additif** : NEW module, 0 modif core/ partagé
- **R6 fail-open** : entrée invalide → 1.0, fallback safe ×0.8
- **R7 tests verts** : 44 tests (43 unit + 1 audit live)
- **R14 git vérité** : audit SQL 60j mesuré, JAMAIS inventer
- **R18 code pur** : pas de LLM, calcul I/O-free
- **R22 sous-unité unique** : 1 module + 1 test + 1 commit
- **R25' motion CEO** : défaut OFF strict

## Gain projeté

60-100 pips / cycle (cf. prompt sprint CEO V5).

## Fichiers

| Fichier | Rôle |
|---|---|
| `core/v9/v9_news_heat_map.py` | Module principal (NEW) |
| `core/v9/kill_switches.py` | Ajout `news_heat_map_enabled()` |
| `config/v9_kill_switches.env` | `V9_NEWS_HEAT_MAP_ENABLED=0` |
| `tests/test_v9_news_heat_map.py` | 44 tests verts |
