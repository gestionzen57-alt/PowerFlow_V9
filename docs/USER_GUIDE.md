# POWERFLOW V9 — USER GUIDE

Auto-genere le 2026-08-04 (sync sprint CEO V5, +2 modules L19+L20, dette -67%)

## Table des matieres

1. Quick start
2. Architecture 4 couches
3. Modules
4. Operations
5. Maintenance
6. Doctrine 48H non-stop

## 1. Quick start

```bash
# Activer venv
cd C:/projet/V9
source .venv/Scripts/activate

# Run tests
python -m pytest tests/ -q -m 'not slow' -p no:cacheprovider

# Lancer dashboard
python scripts/v9_dashboard_enhanced.py

# Phase 61 - Etat systeme
python scripts/v9_phase_tracker.py --status

# Phase 64 - Preflight LIVE
python scripts/v9_real_money_preflight.py
```

## 2. Architecture 4 couches

```
LECTURE (Daily → M1) → DÉCISION (L1-L17) → OPTIMISATION (Boucle) → EXÉCUTION
```

## 3. Modules

### Phase 50-54 — Lecture marché
- `v9_multi_timeframe_reader.py` : 6 TF Daily→M1
- `v9_july_2026_analysis.py` : analyse cloture mensuelle
- `v9_market_anticipation.py` : regime phase + forward projection
- `v9_price_action_context.py` : patterns + S/R

### Phase 58-60 — Chemin critique
- `v9_mt4_candle_bridge.py` : CSV MT4 → DB candles
- `v9_oos_validator.py` : walk-forward 7 folds
- `v9_robustness_checks.py` : bootstrap + Monte Carlo

### Phase 61 — Pilote auto-perpetuant
- `v9_phase_tracker.py` : state persistence
- `v9_auto_plan.py` : prochaine phase generator
- `v9_auto_commit.py` : git ops inline
- `v9_autonomous_loop.py` : boucle 48H non-stop

### Phase 62-66 — Production-grade
- `v9_pipeline_orchestrator.py` : supervisor + DLQ
- `v9_ftmo_compliance.py` : 4% daily + 8% total
- `v9_real_money_preflight.py` : 20+ checks
- `v9_smart_order_router.py` : iceberg + TWAP + VWAP
- `v9_live_metrics.py` : P&L + Greeks + flow

### Phase 67-72 — Intelligence

### Phase 105-145 — Sprint CEO no-stop V3+V4+V5 (03-04/08/2026)

**15 leviers quantiques ON** (L7-L20) :
- L7 Heatmap regime × session
- L8+L9 (autres leviers quantiques)
- L10 Pyramiding V2 STARS/SUPER_STARS
- L11 GBPUSD × Mer boost + Mar blacklist
- L12 Correlation inter-paires × regime
- L13 Adaptive TP/SL vol realized
- L15 Heatmap regime × session × pattern
- L16 Asymétrie WR par direction
- L17 Cross Blacklist GRAMMAR × 3
- L18 Edge Decay Sentinel
- **L19 News Shock Attenuator** (Phase 141, +40-80p)
- **L20 News Heat Map symbol × news_type** (Phase 143, +60-100p)
- V4 zones_state boost (Phase 136)
- Adaptive DD Tracker (Phase 137)
- Regime Live Detector (Phase 138)

**Bénéfice projeté 30j** : +2800-3300 pips (vs +2038-2788 V4 finalisé)

**Dette technique** : 76 F → ~25 F (Phase 144 quick wins, -67%)

**Architecture** : sprint parallélisé Hermes × ZCode validé sur 3 sprints
consécutifs (V3 + V4 + V5).
- `v9_ml_forecaster.py` : features + scoring
- `v9_performance_persistence.py` : trend tracking
- `v9_cross_pair_correlation.py` : pearson matrix
- `v9_chaos_advanced.py` : partition + latency + loss
- `v9_adversarial_testing.py` : NaN/Inf/zero/extreme
- `v9_e2e_pipeline.py` : integration end-to-end

## 4. Operations

### Demarrer la boucle auto-perpetuante
```bash
python scripts/v9_autonomous_loop.py --max-hours 48
```

### Voir avancement
```bash
python scripts/v9_phase_tracker.py --status
```

### Cron 48H perfection
```bash
bash scripts/v9_cron_48h.sh
```

## 5. Maintenance

### Backup DB
```bash
cp data/v9_forces.db backups/v9_forces_$(date +%Y%m%d).db
```

### Regenere INDEX
```bash
python scripts/v9_docs_sync.py --sync
```

## 6. Doctrine 48H non-stop

Cf. `docs/DOCTRINE_48H_NONSTOP.md` :
- R1 : ZERO confirmation
- R2 : boucle continue
- R3 : state persistence
- R4 : auto-commit inline
- R5 : auto-coherence docs
- R6 : auto-priorite
- R7 : auto-terminate

---
Auto-genere via v9_user_guide_enrich.py