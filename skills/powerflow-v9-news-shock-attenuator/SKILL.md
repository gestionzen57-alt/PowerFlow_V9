---
name: powerflow-v9-news-shock-attenuator
description: Use when working on Phase 141 L19 News Shock Attenuator (modulation sizing selon fenetre news NFP/CPI/FOMC).
---

# powerflow-v9-news-shock-attenuator — Phase 141 L19

Module additif (R2) qui module le sizing selon la fenêtre news
(pre_news ×0.5 / imminent ×0.0 HALT / post_news ×0.5 /
normalisation ×0.8 / normal ×1.0).

## Audit SQL live 03/08 (R14, n=337 paper_trades 30j)

| regime | n | WR | PNL total | avg pips/trade |
|---|---|---|---|---|
| normal_spread (1.5-2.0) | 215 | 53.0% | -245.8 pips | -1.14 |
| **wide_spread (2.0-3.0, proxy news)** | **122** | **18.0%** | **-619.4 pips** | **-5.08** |

→ La fenêtre news (wide spread) détruit **2.7× plus** de pips par trade.
WR chute de **35 pts**. Justification empirique directe.

## API

```python
from core.v9.v9_news_shock_attenuator import (
    get_news_window_multiplier,
    classify_news_window,
    news_shock_attenuator_enabled,
    summarize_phase_distribution,
    NewsWindowVerdict,
)
```

### `get_news_window_multiplier(minutes_to_news: int) -> (float, str)`

Logique (bornes spec prompt) :
- `15 <= m <= 60` → `(0.5, "pre_news")`
- `0 <= m < 15` → `(0.0, "imminent")` — HALT
- `-15 <= m < 0` → `(0.5, "post_news")`
- `-60 <= m < -15` → `(0.8, "normalisation")`
- autre → `(1.0, "normal")`

Si kill switch OFF : toujours `(1.0, "kill_switch_off")` (pass-through R25').

## Kill switch

- Variable env : `V9_NEWS_SHOCK_ATTENUATOR_ENABLED`
- Défaut : `0` (R25' strict motion CEO)
- Activation : motion CEO explicite

## Doctrine

- **R2 additif** : NEW module, 0 modif core/ partagé
- **R6 fail-open** : entrée invalide (str/None) → `(1.0, "normal")` sans crash
- **R7 tests verts** : 33 tests (32 unit + 1 audit live)
- **R14 git vérité** : audit SQL mesuré, JAMAIS inventer
- **R18 code pur** : pas de LLM, calcul I/O-free
- **R22 sous-unité unique** : 1 module + 1 test + 1 commit
- **R25' motion CEO** : défaut OFF strict

## Gain projeté

40-80 pips / cycle (cf. prompt sprint CEO V5).

## Fichiers

| Fichier | Rôle |
|---|---|
| `core/v9/v9_news_shock_attenuator.py` | Module principal (NEW) |
| `core/v9/kill_switches.py` | Ajout `news_shock_attenuator_enabled()` |
| `config/v9_kill_switches.env` | `V9_NEWS_SHOCK_ATTENUATOR_ENABLED=0` |
| `tests/test_v9_news_shock_attenuator.py` | 33 tests verts |
