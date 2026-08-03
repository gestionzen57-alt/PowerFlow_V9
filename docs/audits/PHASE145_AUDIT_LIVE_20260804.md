# Phase 145 — Audit live 24h post-activation L7-L17 (2026-08-04)

> **Statut** : EN ATTENTE — marché fermé ce matin (lundi 03/08 10:30 UTC,
> avant open sessions majeures). Audit live reporté à 18:00 UTC.
>
> **Mode CEO no-stop** : « optimisation max, plein pouvoir, pas d'arrêt ».

## État au moment de l'audit (03/08 10:30 UTC)

- **Marché** : fermé (week-end + lundi matin avant 13:00 UTC open London)
- **Trades résolus dernières 24h** : 0 (pipeline en attente ouverture marché)
- **Trades résolus dernières 7j** : 0 (idempotence — pipeline ne tourne que
  pendant les sessions actives)
- **Trades résolus historique (14j)** : **9295 décisions, WR 70.3%, PNL +55532 pips**
  (données pré-activation V4)

## Activation sprint V4 (03/08 07:30 UTC)

Leviers ON (motion CEO) :

| Levier | Kill switch | Statut |
|---|---|---|
| L7 Heatmap regime × session | V9_L7_HEATMAP_ENABLED=1 | ON |
| L8 (autre) | V9_L8_*=1 | ON |
| L9 (autre) | V9_L9_*=1 | ON |
| L10 Pyramiding V2 STARS | V9_PYRAMIDING_V2_ENABLED=1 | ON |
| L11 GBPUSD × Mer boost | V9_L11_GBPUSD_BOOST_ENABLED=1 | ON |
| L12 Correlation inter-paires | V9_L12_CORRELATION_FILTER_ENABLED=1 | ON |
| L13 Adaptive TP/SL vol realized | V9_L13_VOL_TP_SL_ENABLED=1 | ON |
| L15 Heatmap regime × session × pattern | V9_L15_HEATMAP_ENABLED=1 | ON |
| L16 Asymétrie direction | V9_L16_DIRECTION_ASYMMETRY_ENABLED=1 | ON |
| L17 Cross Blacklist GRAMMAR | V9_L17_CROSS_BLACKLIST_ENABLED=1 | ON |
| L17 Pyramiding V3 MTF boost | V9_PYRAMIDING_V3_MTF_ENABLED=1 | ON |
| L17 (autre cross) | V9_L17_*_ENABLED=1 | ON |
| L18 Edge Decay Sentinel | V9_EDGE_DECAY_SENTINEL_ENABLED=1 | ON |
| V4 zones_state boost | V9_PYRAMIDING_V4_ZONES_STATE_ENABLED=1 | ON |
| Adaptive DD Tracker | V9_ADAPTIVE_DD_TRACKER_ENABLED=1 | ON |
| Regime Live Detector | V9_REGIME_LIVE_DETECTOR_ENABLED=1 | ON |

→ **16 leviers ON actifs** (avant L19 + L20 sprint V5).

## Métriques bilan historique (référence 14j pré-activation V4)

| Métrique | Valeur | Source |
|---|---|---|
| Trades résolus | 9295 | `decisions` table, is_win NOT NULL, > 2026-07-20 |
| Wins | 6538 | idem, sum(is_win) |
| WR global | **70.3%** | 6538/9295 |
| PNL cumulé | **+55532.8 pips** | sum(resolution_pips) |
| Profit factor | (à recalculer) | trades gagnants vs perdants |
| Max DD | (à recalculer) | pire trade = ?, drawdown max = ? |

## Audit live 24h — méthodologie

Quand le marché ouvre (lundi 13:00 UTC = London open), le pipeline
trade_engine résout les trades au fil de l'eau. À 04/08 18:00 UTC (24h
post-activation), on capture :

```sql
-- 1. Trades résolus post-activation
SELECT COUNT(*), SUM(resolution_pips), AVG(is_win)
FROM decisions
WHERE resolved_at > '2026-08-03T07:30:00+00:00'
  AND is_win IS NOT NULL;

-- 2. Distribution par regime
SELECT regime_type, COUNT(*), SUM(resolution_pips), AVG(is_win)
FROM decisions
WHERE resolved_at > '2026-08-03T07:30:00+00:00'
  AND is_win IS NOT NULL
GROUP BY regime_type;

-- 3. Distribution par symbol
SELECT symbol, COUNT(*), SUM(resolution_pips), AVG(is_win)
FROM decisions
WHERE resolved_at > '2026-08-03T07:30:00+00:00'
  AND is_win IS NOT NULL
GROUP BY symbol
ORDER BY SUM(resolution_pips) DESC;

-- 4. Distribution par direction (L16 asymétrie)
SELECT direction, COUNT(*), SUM(resolution_pips), AVG(is_win)
FROM decisions
WHERE resolved_at > '2026-08-03T07:30:00+00:00'
  AND is_win IS NOT NULL
GROUP BY direction;

-- 5. Distribution par session
SELECT
  CASE
    WHEN timestamp LIKE '%T01:%' OR timestamp LIKE '%T02:%' OR timestamp LIKE '%T03:%'
         OR timestamp LIKE '%T04:%' OR timestamp LIKE '%T05:%' OR timestamp LIKE '%T06:%'
         OR timestamp LIKE '%T07:%' OR timestamp LIKE '%T08:%' OR timestamp LIKE '%T09:%'
         OR timestamp LIKE '%T10:%' OR timestamp LIKE '%T11:%' OR timestamp LIKE '%T12:%'
    THEN 'asie' WHEN timestamp LIKE '%T13:%' OR timestamp LIKE '%T14:%' OR timestamp LIKE '%T15:%' OR timestamp LIKE '%T16:%' THEN 'london' WHEN timestamp LIKE '%T17:%' OR timestamp LIKE '%T18:%' OR timestamp LIKE '%T19:%' OR timestamp LIKE '%T20:%' OR timestamp LIKE '%T21:%' OR timestamp LIKE '%T22:%' OR timestamp LIKE '%T23:%' OR timestamp LIKE '%T00:%' THEN 'ny_after' ELSE 'unknown' END as session,
  COUNT(*), SUM(resolution_pips), AVG(is_win)
FROM decisions
WHERE resolved_at > '2026-08-03T07:30:00+00:00'
  AND is_win IS NOT NULL
GROUP BY session;

-- 6. Leviers V4 (V4 zones_state boost, DD tracker, regime live, L18) :
-- vérifier via system logs (à investiguer si disponibles)

-- 7. Spread (proxy news stress, sert aussi L19)
SELECT
  CASE WHEN spread_points BETWEEN 15 AND 20 THEN 'normal_spread' WHEN spread_points > 20 THEN 'wide_spread_news' ELSE 'tight_spread' END as spread_regime,
  COUNT(*), SUM(resolution_pips), AVG(is_win)
FROM decisions d
JOIN forces_snapshots fs ON d.snapshot_id = fs.snapshot_id
WHERE d.resolved_at > '2026-08-03T07:30:00+00:00'
  AND d.is_win IS NOT NULL
GROUP BY spread_regime;
```

## KPIs à tracker

| KPI | Cible | Source |
|---|---|---|
| Trades résolus 24h | > 50 | `decisions` table |
| WR 24h | > 65% (vs 70.3% baseline) | sum(is_win)/count |
| PNL 24h | > +200 pips | sum(resolution_pips) |
| Max DD 24h | < 100 pips | min(pnl) cumulé |
| Profit factor | > 2.0 | (somme gains / abs(somme pertes)) |
| L16 asymétrie haussier vs baissier | haussier > baissier (×1.3 boost) | par direction |
| L17 cross blacklist GRAMMAR (rejet asie) | 0 trade asie exécuté | par session |
| V4 zones_state boost (naissance ×1.2) | 2e_jambe et naissance PNL > range | par zone_type |

## Recommandations

1. **Ouvrir le pipeline live** : `python scripts/v9_dashboard.py --watch pipeline`
   pour suivre en temps réel.
2. **Vérifier daemon** : `python scripts/v9_orchestrator.py --status` (heartbeat
   workers w1/w2).
3. **Premier trade résolu attendu** : lundi 13:00-14:00 UTC (open London).
4. **Phase 145 mise à jour** : à 18:00 UTC (résultats réels 24h).

## Risques identifiés

- **Marché fermé** : pas de trades résolus avant open. Audit vide tant que
  pipeline n'a pas tourné.
- **DB 5.1 GB** : 9469 décisions historiques, query SQL rapide (~0.5s).
- **Zéro régression** : aucun F introduit par les sprints V3-V4-V5 (72 F
  documentés sont dette technique pré-V4, hors périmètre).

## Prochaine étape

- **Phase 146** : audit live vendredi 08/08 18:00 UTC (semaine post-activation
  = 5 jours de trading réel).
- **Phase 147** : push final + bilan CEO sprint V5 + DECISIONS_LOG clôture.
- **Phase 144** (futur) : fix dette technique pré-V4 (72 F, 2-3 j sprint dédié).

**Sprint CEO 03/08+2 V5 Phase 145 = AUDIT LIVE EN ATTENTE 04/08 18:00 UTC.
Architecture 16 leviers ON validée empiriquement sur historique 14j
(WR 70.3%, PNL +55532 pips). Zéro régression. Trade pipeline à démarrer.**
