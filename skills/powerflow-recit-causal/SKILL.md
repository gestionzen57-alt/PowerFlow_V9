---
name: powerflow-recit-causal
description: "Pattern 'moteur de récit causal' — transforme un index de scènes en narrative chronologique avec chaîne parent→enfant H4→M5"
version: 1.0.0
author: powerflow-m3-align
tags: [powerflow, scene-db, narrative, causal-chain, multi-tf]
---

# Powerflow Recit Causal

# PowerFlow Récit Causal

## Rôle
Construire la chaîne causale d'une séquence de scènes (H4→M30→M15→M5) avec narrative chronologique, prospective, et pre-cross répulsion. C'est la Phase 7 du chantier Scene DB.

## Quand charger
- Génération d'un briefing live : `get_scene_trajectory(window_id)` → chaîne + narrative.
- Analyse post-session : reconstruire le film du marché sur 2h.
- Backtest épisode : expliquer POURQUOI la fenêtre A1 a mené à B2.

## Composants

### 1. Index de scènes (timeline)
```python
from core.pf_scene_timeline import get_trajectory
traj = get_trajectory(window_id="W_2026_06_25_142300_A1")
# → list of {parent_id, scene_type, tf, ts, direction, narrative}
```

### 2. Chaîne parent→enfant
- H4 = scène parente (contexte macro)
- M30 = basculement HTF (trigger directionnel)
- M15 = pre-cross répulsion (force battle)
- M5 = résolution (entry)

### 3. Narrative chrono (3 lignes max)
```
14:23 H4 USD dominant (z=+1.8) → contexte baissier GBPUSD
14:31 M30 cross M5↔M15 confirmé USD → basculement
14:38 M15 pre-cross répulsion GBP (-15) → rejection zone 1.274
14:42 M5 explosion baissière → entry SHORT validé
```

### 4. Prospective
Probabilités conditionnelles via `get_scene_sequence(scene_a, scene_b)` :
- P[B2 | A1] = 0.62
- P[LOSS | A1→B2] = 0.04 (WR 96% cellule B2 LOW)

## Sortie attendue
Rapport ≤ 200 mots : contexte + chaîne + proba + recommandation GPS.

## Pièges
- Ne JAMAIS inventer de scène absente de la DB → utiliser `get_window(id)`.
- Narrative doit être CAUSALE ("parce que", "donc") pas descriptive.
- Si `parent_scene_id IS NULL` → c'est une racine H4, signaler "début épisode".

