# V7 Sprint Plan — Post-Correctif L8/L9 (2026-08-03)

**Contexte** : CEO autopilote « plein pouvoir » session 03/08 20:18→20:55 UTC.
Désactivation L8+L9 + correction L11 Mer→Ven + 47 tests verts cumulés.

## Verdict urgence Phase 156/157/158

- L8 (n_principes >= 5) : **désactivé**, edge détruit en live (-302.9p)
- L9 (blacklist < 14h UTC) : **désactivé**, drain confirmé (-520p)
- L11 Mer boost : **désactivé**, sprint CEO faux signal (Mer=45% WR, Ven=97.4% WR)
- L11 Ven boost : **activé** (Phase 158, vrai edge)
- L11 Mar blacklist : **conservé** (correct, 0% WR -158p)

## V7 Sprint — 6 phases post-récupération (J+0 à J+7)

### Phase 160 — Re-validation L8/L9 (7j live minimum)

**Périmètre** : re-créer walk-forward L8/L9 en mode LIVE (post-J+1, post-J+7).
But : produire un verdict walk-forward sur trades LIVE, pas re-filtrés a posteriori.

- Délivrable : `scripts/v9_phase160_l8l9_live_walkforward.py`
- Critère GO re-activation : n≥30 + WR≥70% + PNL>+200p sur 7j live
- Motion CEO explicite requise pour re-activation (R25' strict)

### Phase 161 — Activation L19 News Shock Attenuator

**Module** : `core/v9/v9_news_shock_attenuator.py` (Phase 141, livré sprint CEO)
- Kill switch : `V9_NEWS_SHOCK_ATTENUATOR_ENABLED` (défaut OFF)
- Test : 33/33 verts Phase 141
- Gain projeté : +40-80 pips

**Action** : activer après 7j observation Phase 160.

### Phase 162 — Activation L20 News Heat Map

**Module** : `core/v9/v9_news_heat_map.py` (Phase 143, livré sprint CEO)
- Kill switch : `V9_NEWS_HEAT_MAP_ENABLED` (défaut OFF)
- Test : 44/44 verts Phase 143
- Gain projeté : +60-100 pips

**Action** : activer après 7j observation Phase 160.

### Phase 163 — Edge Decay Sentinel + Regime Live Detector

**Modules** :
- `core/v9/v9_edge_decay_sentinel.py` (Phase 140, ZCode2)
- `core/v9/v9_regime_live_detector.py` (Phase 138, Hermes2)

**Gain projeté** : +100-200 pips (60-120p Sentinel + 40-80p Detector)
**Action** : activer après 7j observation Phase 160.

### Phase 164 — V4 Pyramiding (zones_state + DD tracker)

**Modules** : Phase 136 (zones_state boost) + Phase 137 (Adaptive DD tracker)
**Gain projeté** : +130-250 pips (50-100p zones + 80-150p DD)
**Action** : activer après 7j observation Phase 160.

### Phase 165 — Bilan V7 sprint + Go Live Phase 12

**Périmètre** :
- Audit final 30j post-V7
- Verdict go/no-go LIVE FTMO
- Si GO : activer V9_EXECUTION_SIMULATION=0 (mini-lot 0.01)
- Si NO-GO : rester en simulation + plan V8

## Critères succès V7 (à J+7 = 10/08/2026)

| Critère | Cible | Source |
|---|---|---|
| Trades GBPUSD 7j | n>=30 | audit Phase 146 |
| WR GBPUSD 7j | >=70% | audit Phase 146 |
| PNL GBPUSD 7j | >=+200p | audit Phase 146 |
| Walk-forward L8/L9 verdict | REJET/QUASI (pas de re-activation) | Phase 160 |
| L19+L20+Sentinel+RégimeLive+V4 ON | 5/5 leviers | Phases 161-164 |
| Tests verts cumulés | >=100 | tous fichiers |

## Périmètre GELÉ (inchangé depuis V5)

- Phase 10 : Fédération d'agents (gel)
- Skills auto-générés avant canonisation (gel)
- Exécution d'ordres réelle avant Phase 165 verdict (gel)

## Prochaine étape

1. Attendre J+7 (10/08) pour 1ère mesure edge authentique post-correctif
2. Phase 146 audit vendredi 08/08 18:00 UTC (premier audit hebdo)
3. Phase 160 walk-forward L8/L9 live (à partir de J+1)
4. Push progressif Phases 161-165 selon résultats
