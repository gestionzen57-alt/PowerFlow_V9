# POWERFLOW V9 — USER GUIDE

Auto-genere le 2026-08-01

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