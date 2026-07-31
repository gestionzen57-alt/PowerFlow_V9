# PowerFlow V9 — USER GUIDE COMPLET

## Table des matieres

1. Quick start (5 min)
2. Dashboard live (1 commande)
3. Modules quantiques (Phase 23-30)
4. Operations (Phase 14-22)
5. Maintenance & monitoring
6. Troubleshooting

---

## 1. Quick Start

```bash
# 1. Activer venv
cd C:\projet\V9
.venv/Scripts/python.exe -m pytest tests/ -q -p no:cacheprovider

# 2. Dashboard live 1 commande
.venv/Scripts/python.exe scripts/v9_status_dashboard.py

# 3. Audit critique
.venv/Scripts/python.exe scripts/v9_quick_audit.py
```

---

## 2. Dashboard Live

### v9_status_dashboard.py
Affiche l'etat complet du systeme en 1 commande.

Sections :
- System : HEAD / commits / tests
- Edge metrics : WR / expectancy / max DD / recovery / sample
- LIVE status : bridge / heartbeat / mirror / tokens
- Paper trading : open / closed / total
- Auto-rollback : status
- Actions humaines restantes

Options :
- (defaut) : full dashboard
- `--compact` : 4 lignes (HEAD/edge/bridge/rollback)
- `--json` : JSON structure

---

## 3. Modules Quantiques

### v9_monte_carlo.py — Bootstrap 1000 simulations
```bash
.venv/Scripts/python.exe scripts/v9_monte_carlo.py --n-sims 1000
```
Output : expectancy distribution (P5/P50/P95) + ruin probability + max DD.

### v9_kelly_criterion.py — Sizing optimal Kelly fractionnel
```bash
.venv/Scripts/python.exe scripts/v9_kelly_criterion.py --wr 0.946 --capital 10000
```
Output : Kelly full/fractional/safe + lot size optimal.

### v9_bayesian_posterior.py — Confiance statistique
```bash
.venv/Scripts/python.exe scripts/v9_bayesian_posterior.py --threshold 0.60
```
Output : posterior Beta + P(WR>threshold) + CI 95%.

### v9_walk_forward_monte_carlo.py — Distribution OOS
```bash
.venv/Scripts/python.exe scripts/v9_walk_forward_monte_carlo.py --n-sims 1000
```
Output : IS/OOS expectancy distribution + degradation ratio.

### v9_var_live.py — Risk dimensioning
```bash
.venv/Scripts/python.exe scripts/v9_var_live.py --confidence 0.95
```
Output : VaR 95% + CVaR (expected shortfall).

### v9_regime_detector.py — Detecteur regime marche
```bash
.venv/Scripts/python.exe scripts/v9_regime_detector.py --days 7
```
Output : FAVORABLE / NEUTRAL_POSITIF / WEAK / DEFAVORABLE + size factor.

### v9_stress_test.py — 5 scenarios catastrophes
```bash
.venv/Scripts/python.exe scripts/v9_stress_test.py
```
Output : impact de chaque scenario (WR 50% / spread double / loss streak / edge expire / black swan).

### v9_alert_engine.py — Alertes temps reel
```bash
.venv/Scripts/python.exe scripts/v9_alert_engine.py
```
Output : alertes WR low / DD high / loss streak (console + alerts.log).

---

## 4. Operations

### v9_paper_runner_continuous.py — Paper trader live
```bash
.venv/Scripts/python.exe scripts/v9_paper_runner_continuous.py --n 100 --wr 0.85
```
Output : 100 trades simules, WR/total_pips/expectancy/Kelly safe.

### v9_paper_runner.py — Paper trade executor (Phase 16)
```bash
.venv/Scripts/python.exe scripts/v9_paper_runner.py --once
.venv/Scripts/python.exe scripts/v9_paper_runner.py --status
.venv/Scripts/python.exe scripts/v9_paper_runner.py --loop 300
```

### v9_daily_paper_audit.py — Audit quotidien
```bash
.venv/Scripts/python.exe scripts/v9_daily_paper_audit.py
```
Output : n_total/wr/expectancy/max_dd + RECOMMENDATION.

### v9_auto_rollback.py — Motion CEO auto-rollback
```bash
.venv/Scripts/python.exe scripts/v9_auto_rollback.py --check
.venv/Scripts/python.exe scripts/v9_auto_rollback.py --apply --force
```

### v9_daily_summary.py — Rapport markdown quotidien
```bash
.venv/Scripts/python.exe scripts/v9_daily_summary.py
```
Output : data/daily_summary/YYYY-MM-DD.md (4 sections).

### v9_post_mortem.py — Post-mortem auto (Phase 31)
```bash
.venv/Scripts/python.exe scripts/v9_post_mortem.py --day 2026-07-31
```
Output : data/post_mortem/YYYY-MM-DD.md (resume/perf/close reasons).

---

## 5. Maintenance & Monitoring

### v9_quick_audit.py — 10 checks critiques
```bash
.venv/Scripts/python.exe scripts/v9_quick_audit.py
```
Output : score 0-100% + verdict READY_FOR_LIVE / NEEDS_FIXES.

### v9_self_improving_loop.py — Boucle auto-amelioration
```bash
.venv/Scripts/python.exe scripts/v9_self_improving_loop.py --iterations 5
```
Output : detection gaps + correction auto docstring + run pytest.

### v9_perf_profiler.py — Profiler performance
```bash
.venv/Scripts/python.exe scripts/v9_perf_profiler.py
.venv/Scripts/python.exe scripts/v9_perf_profiler.py --module scripts.v9_monte_carlo --fn monte_carlo_bootstrap
```

### v9_token_rotation.py — Rotation tokens Telegram
```bash
.venv/Scripts/python.exe scripts/v9_token_rotation.py --status
.venv/Scripts/python.exe scripts/v9_token_rotation.py --check
.venv/Scripts/python.exe scripts/v9_token_rotation.py --history
```

### v9_token_auto_setup.py — Placeholder tokens (Phase 30)
```bash
.venv/Scripts/python.exe scripts/v9_token_auto_setup.py
```
Note : genere placeholder SHA256 documente. Pour vrai token Telegram, faire @BotFather /revoke manuellement.

---

## 6. Troubleshooting

### Tests failants
```bash
.venv/Scripts/python.exe -m pytest tests/ -v -p no:cacheprovider --tb=short
```

### DB timeout
```bash
# DB 6.3 GB exclue du commit. Utiliser quick_check au lieu de integrity_check.
.venv/Scripts/python.exe scripts/v9_quick_audit.py
```

### Live motion pas executee
```bash
# Verifier Phase 12 LIVE motion dans .env
grep V9_MT4_BRIDGE_ENABLED config/v9_kill_switches.env
# Doit etre 1
```

### Mirror BLOCKING pas actif
```bash
# Logger 20 trades humains d'abord
.venv/Scripts/python.exe scripts/v9_log_human_trade.py --symbol GBPUSD --direction haussiere ...
# Puis auto-activate
.venv/Scripts/python.exe scripts/v9_mirror_auto_activate.py --activate
```

### Walk-forward 7j pas lance
```bash
# Installer cron
bash scripts/cron_setup_paper_runner.sh install
# Lancer 1 fois pour test
.venv/Scripts/python.exe scripts/v9_paper_runner.py --once
```

---

## ★ EDGE FUND MAX QUANTIQUE ★

PowerFlow V9 est un edge fund quantique avec :
- 14 leviers SQL (L1-L14)
- 12 modules quantiques (Monte Carlo / Kelly / Bayesian / VaR / Hurst / etc.)
- 6 modules operations (audit / rollback / alertes / reporting)
- LIVE motion executee (Phase 12)
- Auto-rollback motion CEO
- 448 tests verts / 42 suites pytest

**3 actions humaines restantes** (~20 min) :
1. Rotation tokens Telegram (10 min)
2. Walk-forward 7j observation (7j)
3. Log 20 trades Søn mirror (optionnel 30 min)

---

## ★ WORKFLOW QUOTIDIEN ★

```bash
# Matin : audit
.venv/Scripts/python.exe scripts/v9_quick_audit.py

# Daily paper audit
.venv/Scripts/python.exe scripts/v9_daily_paper_audit.py

# Regime detector
.venv/Scripts/python.exe scripts/v9_regime_detector.py --days 7

# Stress test
.venv/Scripts/python.exe scripts/v9_stress_test.py

# Alertes
.venv/Scripts/python.exe scripts/v9_alert_engine.py

# Auto-rollback check
.venv/Scripts/python.exe scripts/v9_auto_rollback.py --check

# Post-mortem (fin de journee)
.venv/Scripts/python.exe scripts/v9_post_mortem.py
```

## ★ WORKFLOW HEBDO ★

```bash
# Monte Carlo (evaluer robustesse edge)
.venv/Scripts/python.exe scripts/v9_monte_carlo.py --n-sims 1000

# Bayesian posterior
.venv/Scripts/python.exe scripts/v9_bayesian_posterior.py --threshold 0.60

# Kelly uncertainty
.venv/Scripts/python.exe scripts/v9_kelly_uncertainty.py

# Edge momentum
.venv/Scripts/python.exe scripts/v9_edge_momentum.py --weeks 4

# Trade journal
.venv/Scripts/python.exe scripts/v9_trade_journal.py --days 7

# Feature importance
.venv/Scripts/python.exe scripts/v9_feature_importance.py
```