---
name: powerflow-v9-l11-dow-filter
description: Use when analyzing or activating DOW × pair filter (Phase 127 L11).
trigger: "Phase 127 L11, DOW filter, GBPUSD mercredi mardi, day-of-week filter"
category: powerflow-v9
---

# PowerFlow V9 — L11 DOW × pair (Phase 127)

Filtre adaptatif par jour de la semaine × paire. Sprint CEO 03/08/2026.

## Kill switches

- `V9_MEGA_EDGE_L11_DOW_GBPUSD_MER_BOOST_ENABLED=1` : boost sizing x1.3
  sur GBPUSD le mercredi. Audit SQL live : n=111 WR=79.3% PNL=+423.1p.
- `V9_MEGA_EDGE_L11_DOW_GBPUSD_MAR_BLACKLIST_ENABLED=1` : blacklist
  GBPUSD mardi. Audit SQL live : n=20 WR=5.0% PNL=-136.9p.

## Câblage

Le filtre est intégré dans `core/v9/v9_mega_edge_filter.py` (méthode
`mega_edge_evaluation`, après L9 et avant L4). Il requête la table
`forces_snapshots` pour récupérer le timestamp du snapshot, calcule
le DOW (0=lundi...6=dimanche), et applique le boost ou le refus.

## Tests

`tests/test_v9_mega_edge_l11_dow.py` : 5/5 verts (boost ON/OFF, blacklist
ON/OFF, date parsing, registration accesseurs).

## Doctrine

- R2 additif (après L9, avant L4)
- R6 fail-open (DB indisponible → skip silencieux, R6 strict)
- R7 tests verts (5/5 ajoutes)
- R14 git verite (chiffres du SQL reel, pas inventes)
- R22 sous-unite unique (1 livrable = 1 filtre)
- R25' motion CEO explicite (R25' strict)
- R26 DECISIONS_LOG entry dediee
- R28 Hermes git unique