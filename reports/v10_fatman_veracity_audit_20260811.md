# VERDICT FATBOY/FATMAN — Audit de véracité (11/08/2026)

Mandat : plein pouvoir CEO, visée trading réel. AVANT tout ordre, vérifier la
véracité de la lecture de l'indicateur Fatboy (source forces_snapshots).
Résultat : lecture FAITE, edge NON CONFIRMÉ → R10 bloque tout ordre réel.

## 1. Lecture — la source est RÉELLE et FRAÎCHE ✅
- DB `data/v9_forces.db` : max bar_time = 2026-08-11 12:58 UTC (fraîche, collecteur MT4 actif)
- `get_fatman_live('USDCHF','H1')` → source=v9_forces_db, ranks_per_currency complet
- Le module lit bien les 8 colonnes force_* réelles. La lecture fonctionne.

## 2. Cohérence directionnelle SAME-BAR (force vs prix même bougie) ≈ 50% ❌
(force_base > force_quote) vs (close>open) même bougie, 30 barres :
  EURUSD M15 56.7% | USDCAD M15 43.3% | USDJPY M15 46.7% | GBPUSD M15 60.0%
  M30 40-63% | H1 43-67% | H4 33-57%
→ bruit (pièce à pile), aucune paire/TF n'a de cohérence stable.

## 3. Test LEAD (force barre t prédit direction t+1) ≈ 50% ❌
  EURUSD M15 51.1% | GBPUSD M15 52.1% | USDCAD M30 57.1% | EURUSD M30 54.1%
  reste 47-53% → PAS d'edge prédictif brut des forces.

## 4. Pipeline réel émis (signal_generator_live, proxy horizon=3) — A2 ANTI-edge ❌
  n=8680 | global WR 0.482 | PnL +429
  A1: n=46 WR 0.52 | A2: n=53 WR 0.28 (ANTI-PRÉDICTIF) | A3: n=17 WR 0.59 | NONE: n=8564 WR 0.48
→ les signaux "haute conviction" A1 ne battent pas NONE. A2 est pire que pile.

## 5. Replay C21 (WR 0.589 / PF 1.96) — CONTAMINÉ PAR LOOKAHEAD 🔴
`run_replay_c21_validation.py` (feat/hermes-night) rapporte un beau 58.9%,
mais le code `v10_replay_engine.py` :
- `_load_h4_bias` : query force_base ECHEC (colonne inexistante) → fallback pente
  close sur 30 barres H4 `ORDER BY bar_time DESC LIMIT 30` = FIN de période.
  Appliqué à CHAQUE décision M15 du replay → lookahead.
  Quantifié : EURUSD pit_start=0.013 vs lookahead=0.122 (Δ+0.109).
- `fractal_conf = compute_fractal_confluence(...)` : calculé UNE FOIS sur la DB
  complète, réutilisé pour toutes les décisions → lookahead.
→ Le WR 58.9% du replay C21 N'EST PAS fiable pour GO LIVE.

## 5b. FALSIFICATION CONFIRMÉE — replay point-in-time (11/08, Hermes) 🔴
Nouveau runner `scripts/run_replay_pointintime.py` (R2 additif, 0 core modifié) :
h4_bias recalé par barre (bar_time ≤ i) + fractal neutralisé. Résultat :

| Métrique | C21 lookahead | Point-in-time honnête | Δ |
|---|---|---|---|
| WR global | 58.94% | **50.51%** | -8.4pts |
| PF | 1.96 | **1.35** | -0.61 |
| PnL pips | +432 | **+210** | -222 |
| n trades | 151 | 196 | +45 |

BY_LEVEL (PIT) : A1 n=152 WR=0.48 | A2 n=44 WR=0.59

→ L'edge "58.9%" était en grande partie un ARTEFACT de lookahead H4/fractal.
En lecture honnête, WR 50.5% ≈ bruit (aucune prédictivité réelle battue de façon
significative). A1 haute-conviction = 48% (pire que pile). PAS d'edge exploitable.

## 5c. FIX INTÉGRÉ AU CŒUR + CONFIRMATION MOTEUR (11/08, Hermes) ✅
`v10_replay_engine.py` corrigé (R2 additif, paramètre `point_in_time=False` par défaut
→ préserve les 1340 tests) :
- `_h4_bias_pit(conn, symbol, at_bar_time)` : pente close H4 avec bar_time<=i (0 lookahead)
- `_replay_pair_tf(..., point_in_time)` : recalcule h4 par barre + neutralise fractal
- `run_all(..., point_in_time)` : propage le flag
Validation via `ReplayEngine.run_all(point_in_time=...)` :

| Mode | WR | PnL pips | live_ready |
|---|---|---|---|
| POINT-IN-TIME (honnête) | **51.02%** | +209 | False |
| HISTORIQUE (lookahead) | 57.05% | +401 | False |

→ Écart ~6pts WR / ~190 pips = 100% lookahead. `live_ready=False` dans les 2 modes :
le moteur ne se déclare PAS prêt pour le live. 1340/1340 tests verts après fix.

## 6. Modules annoncés manquants 🔴
- `v10_fatman_intelligence_hub.py` (cerveau fusion SOUL.md) : N'EXISTE PAS
- skill powerflow-v10-edge-fund référence attribut `ranks` absent de FatmanLiveState
→ la doc sur-promet vs le code réel.

## VERDICT FINAL
- La LECTURE Fatman est réelle et fraîche. ✅
- L'EDGE prédictif des forces N'EST PAS confirmé : brut ≈50%, A2 anti-edge (proxy),
  et le replay point-in-time honnête donne WR 50.5% / PF 1.35 (≈ bruit). ❌
- Le chiffre qui battait le bruit (replay C21 58.9%) était un ARTEFACT de
  lookahead H4 + fractal (falsifié par replay point-in-time : -8.4pts WR). ❌
- **R10 BLOQUE** : zéro ordre réel. GO LIVE non justifié. Le levier max demandé
  ne s'applique qu'à un edge Prouvé — ce n'est pas le cas.

## Recommandation clairvoyante
1. **NE PAS trader réel** sur la lecture Fatman seule — edge non prouvé (50.5%).
2. Corriger `v10_replay_engine._replay_pair_tf` : h4_bias PIT par barre + fractal PIT,
   puis rejouer. (Le runner point-in-time prouve la méthode ; à intégrer au cœur.)
3. A2 M15 PIT = 59% (n=44) : piste à investiguer, mais n trop faible + instable.
4. L'edge réel (si existe) doit être re-trouvé SANS lookahead, validé en
   walk-forward hors-échantillon, AVANT micro-lot 0.01. R10.
5. Alerte Telegram/CEO immédiate (ne pas attendre).

Rapport R9 — généré par Hermes, 11/08/2026. Falsification replay PIT incluse.
