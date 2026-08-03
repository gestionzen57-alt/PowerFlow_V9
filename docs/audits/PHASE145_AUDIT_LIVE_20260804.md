# Phase 145 — Audit live post-activation L7-L18 (2026-08-04)

> **Statut** : MARCHÉ OUVERT (depuis dimanche 02/08 21:00 UTC) mais **PIPELINE
> INACTIF** — orchestrator state stale depuis 01/08 08:28 UTC.
> 0 trade résolu depuis l'open.
> **Marché** : actuellement lundi 03/08 13:15 UTC = London open actif.
> **Pipeline** : workers w1/w2 status "alive" mais last_heartbeat = 01/08 08:28.

## État au moment de l'audit (03/08 13:15 UTC)

### Pipeline live (data/orchestrator_state.json)

| Worker | Status | Last heartbeat |
|---|---|---|
| w1 | alive | 2026-08-01T08:28:13 (vendredi 01/08) |
| w2 | alive | 2026-08-01T08:28:13 (vendredi 01/08) |
| Crashes | 0 | — |
| Restart attempts | 0 | — |
| Global status | **idle** | dernière maj 2026-08-01T08:28 |

**Conclusion** : orchestrator inactif depuis 2 jours 5h. Pas de résolution
de trades en cours. Workers stale.

### Trades depuis l'open (dimanche 02/08 21:00 UTC → maintenant)

| Table | Fenêtre | N | Wins | WR | PNL |
|---|---|---|---|---|---|
| `decisions` | depuis 02/08 21:00 | **0** | 0 | 0% | None |
| `decisions` | 24h | **0** | 0 | 0% | None |
| `decisions` | 14j historique | 9295 | 6538 | 70.3% | +55532.8p |
| `paper_trades` | depuis 02/08 21:00 | **0** | — | — | — |
| `paper_trades` | all-time (337) | 337 | 150 | 44.5% | -865.15p |

**Constat critique** : 0 trade résolu depuis l'open dimanche soir. Le
pipeline live trading a cessé son activité le 01/08 19:46 UTC (dernier
paper_trade closed). 2 jours 17h sans activité.

### Décisions non résolues (backlog)

| Table | Total | Unresolved | % unresolved |
|---|---|---|---|
| `decisions` | 104140 | 94671 | 90.9% |
| `paper_trades` | 337 | 0 | 0% |

**94671 décisions non résolues (90.9% du backlog)** — backlog legacy
depuis juillet 2026, pas un problème post-V4. Le pipeline de résolution
a tourné en juillet mais semble être arrêté depuis.

## Phase 145 — Méthodologie audit live (en attente activation pipeline)

Quand le pipeline est activé (motion CEO requise, R25' strict), 7 queries
SQL prêtes pour capturer les trades live :

```sql
-- 1. Trades résolus post-activation L7-L18
SELECT COUNT(*), SUM(resolution_pips), AVG(is_win)
FROM decisions
WHERE resolved_at > '2026-08-04T18:00:00+00:00'
  AND is_win IS NOT NULL;

-- 2. Distribution par regime
SELECT regime_type, COUNT(*), SUM(resolution_pips), AVG(is_win)
FROM decisions
WHERE resolved_at > '2026-08-04T18:00:00+00:00'
  AND is_win IS NOT NULL
GROUP BY regime_type;

-- 3. Distribution par symbol
SELECT symbol, COUNT(*), SUM(resolution_pips), AVG(is_win)
FROM decisions
WHERE resolved_at > '2026-08-04T18:00:00+00:00'
  AND is_win IS NOT NULL
GROUP BY symbol
ORDER BY SUM(resolution_pips) DESC;

-- 4. Distribution par direction (L16 asymétrie)
SELECT direction, COUNT(*), SUM(resolution_pips), AVG(is_win)
FROM decisions
WHERE resolved_at > '2026-08-04T18:00:00+00:00'
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
WHERE resolved_at > '2026-08-04T18:00:00+00:00'
  AND is_win IS NOT NULL
GROUP BY session;

-- 6. Spread (proxy news stress, sert aussi L19)
SELECT
  CASE WHEN spread_points BETWEEN 15 AND 20 THEN 'normal_spread' WHEN spread_points > 20 THEN 'wide_spread_news' ELSE 'tight_spread' END as spread_regime,
  COUNT(*), SUM(resolution_pips), AVG(is_win)
FROM decisions d
JOIN forces_snapshots fs ON d.snapshot_id = fs.snapshot_id
WHERE d.resolved_at > '2026-08-04T18:00:00+00:00'
  AND d.is_win IS NOT NULL
GROUP BY spread_regime;

-- 7. PNL cumulé live (24h)
SELECT
  SUM(resolution_pips) as pnl_24h,
  MAX(resolution_pips) as best_trade,
  MIN(resolution_pips) as worst_trade,
  COUNT(DISTINCT symbol) as symbols_traded
FROM decisions
WHERE resolved_at > '2026-08-04T18:00:00+00:00'
  AND is_win IS NOT NULL;
```

## KPIs cibles (post-activation)

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

### Court terme (urgent — pipeline inactif)

1. **Activer le pipeline live** : motion CEO explicite requise
   (R25' strict, kill switch `V9_EXECUTION_ENABLED`).
2. **Relancer l'orchestrator** : `python scripts/v9_resolve_decision_auto_daemon.py`
   (script daemon disponible, en attente activation).
3. **Vérifier heartbeat** : `python scripts/v9_orchestrator_state.py --status`
   (à créer si pas existant).

### Moyen terme (Phase 145 → 146)

1. **Une fois pipeline actif** : laisser tourner 24h puis capturer
   les 7 queries SQL ci-dessus.
2. **Phase 145 mise à jour** : remplacer ce fichier avec résultats
   réels dès que trades résolus.
3. **Phase 146** : audit live vendredi 08/08 18:00 UTC (semaine).

### Risques identifiés

- **Pipeline inactif** : depuis 01/08 19:46 UTC = 2j 17h. Impact : 0
  trade résolu pendant l'open du marché. Bénéfice projeté 30j +2800-3300p
  NON RÉALISÉ.
- **94671 décisions backlog** : legacy, hors périmètre sprint CEO V5.
- **Marché ouvert** : window London active (13:00-16:00 UTC) puis NY (17:00-22:00 UTC).
  Trades attendus si pipeline actif.

## Phase 145 — Action immédiate

**NE PAS ACTIVER LE PIPELINE SANS MOTION CEO EXPLICITE** (R25' strict).

L'orchestrator est en mode `idle` et le heartbeat stale depuis 01/08.
L'activation live nécessite :
1. Motion CEO dans DECISIONS_LOG.md
2. Kill switch `V9_EXECUTION_ENABLED=1` (défaut OFF)
3. Lancement du daemon : `python scripts/v9_resolve_decision_auto_daemon.py &`
4. Heartbeat à 30s pour vérifier status workers

**Recommandation CEO** : motion explicite pour activation live
"R25' L7-L18 ON (audit live Phase 145-146)" puis activation des
kill switches L7-L18, puis activation L19+L20 (news shock + heat map)
en mode SHADOW d'abord (motion séparée).

## Statut Phase 145

| Élément | Statut |
|---|---|
| Marché ouvert | ✅ OUI (depuis 02/08 21:00 UTC) |
| Pipeline live | ❌ INACTIF (heartbeat 01/08 08:28) |
| Trades résolus 24h | 0 (DB) |
| Audit SQL queries prêtes | ✅ 7 queries prêtes |
| Motion CEO activation | ❌ NON REÇUE (R25' strict) |
| Phase 146 audit live | En attente (08/08 18:00 UTC) |

**Phase 145 = EN ATTENTE MOTION CEO pour activation pipeline live.**
**Sprint CEO V5 finalisé (37 commits, 15 leviers, dette -67%, +2800-3300p).**
**Phase 146 audit live vendredi 08/08 18:00 UTC en attente.**
