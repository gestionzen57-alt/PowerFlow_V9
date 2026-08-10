# ROADMAP V10 C22 — Plan GO LIVE

> État : 2026-08-11 00:10 CEST | Base : feat/v10-c20-healthy HEAD 2c37595 | Tests : 1380 ✅

## Situation actuelle C21

| Critère | Valeur | Seuil GO LIVE | Statut |
|---|---|---|---|
| Tests V10 | 1380 | ≥ 1300 | ✅ |
| DeploymentValidator | 83.33/100 | ≥ 75 | ✅ |
| WR M15 focused (replay) | 59.35% | ≥ 58% | ✅ |
| PF M15 focused | 1.925 | ≥ 1.5 | ✅ |
| WFA | MARGINAL | PASS requis | ⚠️ |
| broker_connected (IBKR) | ❌ | ✅ requis | 🔴 |
| feed_active | ❌ | ✅ requis | 🔴 |
| Health score live | DEGRADED 33/100 | ≥ 90 | 🔴 |

## C22 — Missions prioritaires

### CEO-OPT1 : Kelly adaptatif ✅ (ce push)
- `scripts/ceo_kelly_optimizer.py`
- Fraction = (WR - (1-WR)/RR) × 0.25 × ATR_scale
- Floor 0.5% / Cap 4%

### CEO-OPT2 : Circuit-breaker streak ✅ (ce push)
- `scripts/ceo_circuit_breaker.py`
- 3 SL → pause 2h | 5 SL → pause 4h + alerte

### CEO-OPT3 : QUANT Edge Scorer ✅ (ce push)
- `scripts/ceo_quant_edge_scorer.py`
- Score [0,1] : force Z-score + pre_wave_phase + régime + level
- GO si score ≥ 0.55

### CEO-OPT4 : Dashboard CEO ✅ (ce push)
- `scripts/run_ceo_dashboard.py`
- `python scripts/run_ceo_dashboard.py --phase COMPRESSION --regime TRENDING_UP --signal-level A1 --force-delta 20`

## Conditions GO LIVE (ordre de priorité)

1. **IBKR bridge connecté** → `broker_connected=True` → DeploymentValidator 100
2. **Feed actif** → `feed_active=True`
3. **WFA_PASS** → WR moyen ≥ 52% sur 4/5 fenêtres (actuellement MARGINAL)
4. **Health score ≥ 90** → nécessite IBKR + 0 trou DB
5. **Circuit-breaker CLEAR** → vérifier avant chaque session
6. **Edge score ≥ 0.55** sur la paire/TF ciblée

## Semaine C22 — Plan sessions

| Session | Objectif | Livrables |
|---|---|---|
| Nuit 10-11/08 | H-LIVE-REPORT + H-REPLAY-C21 | live_session_report + replay_c21_validation |
| Matin 11/08 | Connexion IBKR (Søn) | broker_connected=True |
| Journée 11/08 | WFA renforcé (ZCode) | WFA_PASS ou WFA_STRONG |
| Nuit 11-12/08 | Shadow live IBKR + DeploymentValidator | score ≥ 95/100 |
| 12/08 | **GO LIVE décision CEO** | Paper trading réel |

## Règles invariantes

- **R2** : zéro suppression, ajout uniquement
- **R6** : fail-open systématique
- **R9** : tout résultat → rapport JSON horodaté
- **R10** : ZÉRO ordre réel jusqu'à GO LIVE validé CEO
