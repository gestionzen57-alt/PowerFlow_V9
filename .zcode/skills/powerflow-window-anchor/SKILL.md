---
name: powerflow-window-anchor
description: "Codage détecteurs de fenêtres ancrées (A1, A2, A3, A4, B1) — patterns d'entrée multi-TF qui déclenchent une ancre Scene DB"
version: 1.0.0
author: powerflow-m3-align
tags: [powerflow, scene-db, window-detector, multi-tf, GBPUSD]
statut: legacy-v8
derniere_maj: 2026-07-09
---
# Powerflow Window Anchor

# PowerFlow Window Anchor

## Rôle
Définir et coder les détecteurs de fenêtres ancrées — motifs d'entrée multi-timeframe (H4→M30→M15→M5) qui déclenchent une ancre Scene DB dans `core/scenes.db` (table `windows_journal`).

## Quand charger
- Phase N ≥ 2 : implémentation d'un nouveau type de fenêtre (ex A3, B2, C1).
- Bug fix : faux positifs/négatifs sur détecteur existant.
- Calibration WR : recalcul P[WIN] d'une fenêtre après accumulation de résolutions.

## Format de codage (à appliquer pour chaque fenêtre)

### 1. Signature comportementale (5 dimensions)
- **direction** : BULLISH / BEARISH / RANGE
- **energy** : EXPLOSION / REJECTION / COMPRESSION / EQUILIBRIUM
- **context** : PRE_SESSION / OPENING_DRIVE / MID_SESSION / OVERLAP / CLOSING
- **structure** : BREAKOUT / PULLBACK / REVERSAL / CONTINUATION
- **confirmation** : M5 / M15 / M30 / H1 — TF qui confirme le signal

### 2. Conditions d'entrée (filtres durs)
```python
def detect_A1(ctx):
    return (
        ctx.force_gbp.delta_trend_15 > 15
        and ctx.force_usd.delta_trend_15 < -10
        and ctx.m5.energy_type == "EXPLOSION"
        and ctx.m15.cross_status == "USD_FORMING"
        and ctx.session in ("LONDON_OPEN", "NY_OPEN")
        and ctx.zscore_gbp > 1.5
    )
```

### 3. Ancrage
- Écrire dans `windows_journal` via `core/pf_anchor_detector.py`
- Champs : ts, symbol, scene_type, timeframe, direction, energy, price, metadata JSON

### 4. Calibration
- `core/pf_window_calibration.py --window A1 --days 30`
- WR cible ≥ 55% pour activation prod

## Taxonomie officielle (31 fenêtres)
Voir `docs/TAXONOMIE_FENETRES_TEMPORELLES.md`. Codage actuel : A1, A2, A3, A4, B1.

## Pièges
- HARDCODE `symbol='GBPUSD'` partout (mono-symbole, cf. INVARIANT).
- Ancrer sur M5 cross AVANT confirmation M15 → trop de faux positifs.
- Oublier `timeframe` dans WHERE SQL → UNKNOWN=578 (fix UNKNOWN, #157).

