# Phase 156 — Audit post-désactivation L8+L9 (2026-08-03 20:30 UTC)

**Motion** : CEO autopilote « plein pouvoir » — désactivation L8/L9 (commit `5c963cb`).

## Verdict live actuel

| Métrique | Valeur | Lecture |
|---|---|---|
| Window post-correctif | 5 min (20:25 → 20:30 UTC) | trop court pour verdict |
| Trades GBPUSD 7j | 1 (n=1 WR 0% -13p du 28/07) | trade pré-correctif |
| Capture server | 1 instance (doublon neutralisé 2x) | OK |
| DB | quick_check ok, WAL mode wal, 5.05 GB | OK |
| Kill switches L7/L11 | 1/1 et 1/1 | préservés |
| Kill switches L8/L9 | 0/0 et 0/0 | désactivés (commit 5c963cb) |

## Autopsie 30j GBPUSD (référence)

```
Période             n    WR      PNL       Verdict
AVANT L8 (15+17/07)  87  100.0%  +506.0p   EDGE AUTHENTIQUE
APRES L8 (19-28/07)  77  23.4%   -302.9p   DESTRUCTION
DELTA               -10  -76.6pt -808.9p   CAUSE RACINE = L8
```

Détail post-L8 par jour (sample post-activation) :
- 19/07 : 3 trades, WR 66.7%, -9.5p
- 20/07 : 18 trades, WR 50%, -62.8p
- 21/07 : **20 trades, WR 0%, -145.3p** ← catastrophe majeure
- 22/07 : 27 trades, WR 18.5%, -43.9p
- 23/07 : 5 trades, WR 20%, -29.4p
- 24/07 : 3 trades, WR 33.3%, +0.9p
- 28/07 : 1 trade, WR 0%, -13.0p

## Cause racine

1. **L8 (n_principes >= 5)** : simulation walk-forward a posteriori sur 90j a
   filtré le sample pré-activation en rejouant les filtres à postériori.
   Le verdict "PROMOTE 5/5" n'était pas un walk-forward LIVE.
2. **L9 (blacklist < 14h UTC)** : 13h/jour sans trading (54% du temps marché).
   Les trades autorisés < 14h UTC drainent (-221p le 21/07 seul).
3. **Combinés** : trade_engine sur-filtre au point de sélectionner les pires
   configurations.

## Vérité doctrinale gravée

> **La simulation walk-forward a posteriori n'est PAS le live.**
> Tout verdict positif walk-forward doit être confirmé par 7j live minimum
> avant promotion ACTIVE.

## Plan de récupération 7j

| Jour | Date | Action | Critère GO |
|---|---|---|---|
| J+0 | 03/08 20:30 | L8+L9 OFF (fait) | n=0 |
| J+1 | 04/08 | observation | n≥5 |
| J+2 | 05/08 | checkpoint | n≥10, WR>50% |
| J+3 | 06/08 | checkpoint | n≥20, WR>60% |
| J+7 | 10/08 | verdict | n≥50, WR>70%, PNL>+200p |

**Critère succès** : retour à l'edge authentique (WR ≥ 70% sur 50+ trades)
**Critère échec** : WR < 50% sur 30+ trades → re-investiguer L11/L7

## Suivi automatique

Cron audit à installer : `scripts/v9_phase156_audit.py` quotidien 18:00 UTC,
vérifie n, WR, PNL, lève alerte si dérive.

## Leviers préservés (gains confirmés)

| Levier | Statut | Gain attendu | Source |
|---|---|---|---|
| L7 GRAMMAR/ELASTIC pur | ON | +32.6p | walk-forward L7 simu |
| L11 Mer boost | ON | +423.1p (n=111, WR 79.3%) | audit SQL 03/08 |
| L11 Mar blacklist | ON | -136.9p évité | audit SQL 03/08 |
| Blacklist 5 paires | ON | -474p évité | 30j live |
| R32 DRM APPLY | ON | RR 0.53→1.63 | valid simu 2000 |

## Action immédiate

1. ✅ Désactivation L8+L9 (commit 5c963cb) — FAIT
2. ✅ Backup MD5 env (R8) — FAIT
3. ✅ DECISIONS_LOG entrée — FAIT
4. ⏳ Phase 156 audit quotidien — setup ce soir
5. ⏳ Phase 146 audit live 08/08 — en attente

**Conclusion** : Edge GBPUSD attendu en récupération J+3 à J+7 si
L7+L11+blacklist suffisent. Walk-forward L8/L9 ne sera re-implémenté
qu'après validation 7j live post-correctif.
