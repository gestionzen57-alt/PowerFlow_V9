# PLAN QUANTIQUE L11+ — Saut quantique PowerFlow V9 (2026-08-03)

> **Mission CEO no-stop 03/08** : « optimisation max, plein pouvoir, pas
> d'arrêt ». Le système Phase 12 FTMO est opérationnel avec 9 leviers
> institutionnels ON (L7 + L8 + L9 + Pyramiding V2 + Auto-calibrator +
> Regime gate + Bear perception + Trader mini + Adaptive thresholds).
> Bénéfice mesuré **+758.5 pips** (L7+L8 walk-forward L8 PROMOTE 5/5).
>
> **Question stratégique** : quel(s) levier(s) L11+ apportent un saut
> quantique marginal au-delà des 9 leviers déjà actifs ?

## Inventaire des leviers L1-L9 (rappel)

| Levier | Phase | Gain mesuré | Statut |
|---|---|---|---|
| L1 MEGA-EDGE GBPUSD haussière 11-13h UTC | 108 | +336.5p / 74 trades (WR 94.6%) | **ON** (mega_edge master) |
| L2 KILL HOURS NOIRES 00-09h UTC | 108 | -265p économisés (60 trades KO) | **ON** (mega_edge master) |
| L3 TIME_EXIT < 5min | 108 | WR 57.5% +147p vs -407p | **ON** (mega_edge master) |
| L4 STARS-ONLY 3 stars purs | 108 | WR 100% +440p (76 trades) | **ON** (mega_edge master) |
| L5 BLACKLIST MIX GRAMMAR+ELASTIC | 108 | WR 33% -39p | **ON** (mega_edge master) |
| L6 13h UTC BOOST x1.5 sizing | 108 | WR 94.1% +184p (34 trades) | **ON** (mega_edge master) |
| **L7** GRAMMAR/ELASTIC pur no-stars | 108/117 | **+32.6p** (10 trades bloqués) | **ON** |
| **L8** n_principes >= 5 | 120/121 | **+725.9p** (247/337 bloqués) | **ON** |
| **L9** Blacklist < 14h UTC | 125/03/08 | **+520p projeté** (13h/jour bloqué) | **ON** |
| Total cumulé L7+L8+L9 | — | **+1278.5p potentiel** | 9 leviers ON |

## Plan L11+ — 6 candidats (par priorité ROI)

### L11 — Filtre symétrie (DOW × pattern)

**Hypothèse** : la performance varie selon le jour de la semaine. Le L14
(mardi blacklist GBPUSD haussière, audit 21 trades WR 0% -158p) est déjà
intégré au mega_edge_filter (lignes 220-256). Reste à étendre aux autres
paires et patterns.

**Gain projeté** : 100-200p si on identifie 1-2 jours supplémentaires
(W Lun, J Ven, S Dim = niches WR 80%+, vs M Mardi = -158p).

**Effort** : 1-2 j (audit SQL DOW × pair × direction × pattern, 90j).

**Statut** : ⏸ À lancer — dépend de marché ouvert (data live).

### L12 — Filtre corrélation inter-paires (Phase hedge fund)

**Hypothèse** : 2 paires corrélées > 0.7 → sizing ×0.5 (PRM câblé mais
générique). Affiner par régime (corrélation monte en risk-on/off).

**Gain projeté** : 80-150p (réduction exposition sur fenêtres corrélées).

**Effort** : 2-3 j (extension `v9_drawdown_protector.py` + tests).

**Statut** : ⏸ En attente audit L13 (L11 → L12 → L13 par ordre).

### L13 — Adaptive TP/SL par volatilité realized (post-trade)

**Hypothèse** : ajuster TP/SL non seulement par phase cycle (R32 DRM) et
par session, mais aussi par la volatilité réalisée des 5 dernières bougies.

**Gain projeté** : 50-100p (capture des spikes vol sans casser la RR cible).

**Effort** : 3-5 j (extension `core/v9/dynamic_tp_sl.py`).

**Statut** : ⏸ Moyen terme.

### L14 — Blacklist DOW (déjà livré, L11 en est l'extension)

**Livré Phase 9** : mardi GBPUSD haussière blacklisté (-158p économisés).
Mécanisme dans `v9_mega_edge_filter.py:220-256`.

**Statut** : ✅ ACTIF.

### L15 — Filtre régime × session × pattern (Phase 12 FTMO focus)

**Hypothèse** : cross-analyse regime (CASSURE/EXTENSION/DISTRIBUTION/CLIMAX)
× session (asie/london/overlap/ny/after) × pattern (3-stars/GRAMMAR/mega-edge).

**Gain projeté** : 200-400p (heatmap WR/pips par 96 contextes).

**Effort** : 5-7 j (heatmap complet + 26 tests).

**Statut** : 🔥 PRIORITÉ CEO — heatmap = guide priorisation Phase 13.

### L16 — Asymétrie WR par direction (post-Bear Perception)

**Hypothèse** : WR baissier < WR haussier structurellement (87% vs 98% sur
1108 trades haussier vs 1% baissier catastrophique pré-DROP). Forcer
l'asymétrie dans le sizing (×1.3 haussier, ×0.7 baissier).

**Gain projeté** : 100-250p (en lien avec V9_NO_BAISSIERE=1 mais adaptable).

**Effort** : 2-3 j (extension `core/v9/learning_offset_applier.py`).

**Statut** : ⏸ Moyen terme.

## Recommandation CEO — Sprint L11+ (5 phases)

| Phase | Levier | Effort | ROI | Priorité |
|---|---|---|---|---|
| **Phase 126** | L15 heatmap régime×session×pattern | 5-7 j | 🔥🔥🔥 200-400p | **P0** |
| **Phase 127** | L11 extension DOW × pair | 1-2 j | 🔥🔥 100-200p | **P1** |
| **Phase 128** | L12 corrélation inter-paires × régime | 2-3 j | 🔥🔥 80-150p | **P2** |
| **Phase 129** | L16 asymétrie WR par direction | 2-3 j | 🔥🔥 100-250p | **P2** |
| **Phase 130** | L13 adaptive TP/SL vol realized | 3-5 j | 🔥 50-100p | **P3** |

**Gain cumulé L11-L16 projeté** : **530-1100 pips** sur fenêtre 30j
post-activation.

## Sprint immédiat (Phase 126 — heatmap L15)

**Périmètre R22 strict** :
1. Audit SQL `v9_forces.db` : 96 croisements (4 regimes × 4 sessions × 6 paires)
2. Génération heatmap WR/PNL par contexte → `data/heatmaps/l15_regime_session_pattern.json`
3. Identification des **niches structurelles** (WR > 70% ET n >= 30)
4. Proposition 3-5 nouveaux kill switches basés sur la heatmap
5. Walk-forward 30j pour validation empirique

**Livrables** :
- `scripts/v9_heatmap_l15.py` (CLI heatmap generator)
- `data/heatmaps/l15_regime_session_pattern.json`
- `docs/audits/l15_heatmap_proposal_20260803.md`
- `tests/test_v9_heatmap_l15.py` (tests unitaires)
- 3-5 nouveaux kill switches (R6 fail-open, R25' motion CEO)

**Effort estimé** : 5-7 j CEO no-stop.

## Métriques de succès

| Métrique | Actuel | Cible Phase 126-130 |
|---|---|---|
| Paper trades résolus | 337 | 2000+ |
| WR global post-L7+L8 | 95.56% (n=90) | >= 80% (n >= 500) |
| PNL cumulé 30j | +466.2p (post-L8) | >= +1500p (post-L15) |
| Sharpe-like | 0.845 | >= 1.2 |
| Max DD | -286p | <= -200p |
| Leviers institutionnels ON | 9 | 14-15 (L11-L15) |

## Doctrine

- **R2 additif** : chaque L11+ est un kill switch + module additif
- **R6 fail-open** : défaut OFF, activation = motion CEO
- **R7 tests verts** : 81/81 verts préservés minimum
- **R25' motion CEO** : activation explicite, jamais automatique
- **R26 DECISIONS_LOG** : 1 entrée par phase L11+
- **R28 Hermes git unique** : tous commits via ce canal

## Statut

🚀 **PHASE 126 À LANCER IMMÉDIATEMENT** (motion CEO « plein pouvoir »).

Doctrine : R14 git vérité, R22 sous-unité par phase, R25' motion CEO
explicite, R26 DECISIONS_LOG entry dédie, R28 Hermes git unique.

---

_Référence : `docs/ROADMAP.md` V2 24/24 effectués → V3 L11-L16 proposée._
