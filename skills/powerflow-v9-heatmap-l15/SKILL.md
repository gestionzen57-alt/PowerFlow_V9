---
name: powerflow-v9-heatmap-l15
description: Use when analyzing regime × session × pattern heatmaps (Phase 126 L15).
trigger: "Phase 126 heatmap, L15 heatmap, regime session pattern niche"
category: powerflow-v9
---

# PowerFlow V9 — Heatmap L15 (Phase 126)

Heatmap multi-dimensionnel `regime × session × pattern` pour identifier
les niches structurelles exploitables. Sprint CEO no-stop 03/08/2026.

## Script CLI

```bash
python scripts/v9_heatmap_l15.py [--min-n 10] [--min-wr 70.0] \
    [--output data/heatmaps/l15_regime_session_pattern.json] \
    [--report data/heatmaps/l15_heatmap_report.md]
```

## Sorties

1. `data/heatmaps/l15_regime_session_pattern.json` : heatmap 3D + 2D +
   niches détectées + kill switches proposés (tuple keys sérialisés en
   strings).
2. `data/heatmaps/l15_heatmap_report.md` : rapport lisible avec top niches.

## Niche = WR >= min_wr ET n >= min_n

Défauts : WR >= 70%, n >= 10.

## Kill switches proposés

- `BOOST` : sizing_multiplier = 1.3 sur top niches (WR >= 80% ET n >= 20).
- `BLACKLIST` : sizing_multiplier = 0.0 sur anti-niches (WR < 30% ET n >= 15).

Tous défauts OFF (R25' strict), motion CEO requise pour activation.

## Doctrine

- R2 additif (0 modif core/, lecture seule DB)
- R6 fail-open (DB absente → exit code 4)
- R7 tests verts (8/8 ajoutes)
- R14 git verite (chiffres du SQL reel)
- R22 sous-unite unique
- R25' motion CEO explicite
- R26 DECISIONS_LOG entry dediee
- R28 Hermes git unique