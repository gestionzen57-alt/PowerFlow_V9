---
name: powerflow-v9-edge-decay-sentinel
description: Use when working on Phase 140 L18 (Edge Decay Sentinel, proactive decay detection).
trigger: "Phase 140 L18, edge decay sentinel, decay detection, ZCode2 C1"
category: powerflow-v9
---

# PowerFlow V9 — L18 Edge Decay Sentinel (Phase 140)

Sentinel **proactif** qui détecte la dégradation d'edge AVANT que le WR
ne chute significativement. Sprint CEO 03/08+1 (V4, livré ZCode2 C1).

## Kill switch

- `V9_EDGE_DECAY_SENTINEL_ENABLED=1` (motion CEO Søn 03/08 active)

## Module

`core/v9/v9_edge_decay_sentinel.py` (NEW Phase 140, livré par ZCode2 C1, 303 LOC).

API :
- `edge_decay_sentinel_enabled() -> bool`
- `analyze_principle_decay(principle_id, n_recent=20, n_baseline=100) -> dict`
- `scan_all_principles_decay(n_recent=20, n_baseline=100) -> list[dict]`
- `summarize_scan(scan_results) -> dict`
- `DecayReport` : dataclass avec princip_id, wr_delta, pnl_delta, decay_score, recommended_action

## Logique de détection

| Condition | Action recommandée |
|---|---|
| WR drop ≥ 15% sur 20 derniers vs 100 baseline | BLACKLIST_TEMP_24H |
| PNL recent < 0 sur 30 derniers | DEMOTION_ACTIVE_TO_DORMANT |
| WR drop 5-15% | OBSERVATION_ONLY |
| Stable | PASS_THROUGH |

## Gain projeté

60-120 pips (prévention vs réactif : agit avant que la perte ne s'accumule).

## Tests

`tests/test_v9_edge_decay_sentinel.py` : 19/19 verts (kill switch OFF/ON,
principe stable, decay severe blacklist, pnl negative demotion, decay mild
observation, scan sorted by decay_score desc, R6 fail-open DB absent,
insufficient trades pass-through, audit live DB principles in decay).

## Doctrine

- R2 additif (NEW module, 0 modif core/ partagé)
- R6 fail-open (kill switch OFF, DB absente, données insuffisantes → [])
- R7 tests verts (19/19 ajoutés)
- R14 git vérité (audit SQL live)
- R22 sous-unité unique
- R25' motion CEO explicite (kill switch ON par motion Søn)
- R28 Hermes git unique (ZCode2 livraison C1)