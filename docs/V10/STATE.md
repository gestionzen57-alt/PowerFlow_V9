# V10 STATE — État du pipeline cognitif V10

**Dernière mise à jour** : 2026-08-10 22:30 UTC — Hermes (NO-LIMIT — H-LIVE-REPORT + H-REPLAY-C21)
**Branche active** : `feat/hermes-night`
**HEAD courant** : `99159b9` (H-REPLAY-C21) — **1401/1401 tests V10 verts**

> Gouvernance : `docs/V10/DOCUMENT_STATUS.md` définit les documents actifs et la hiérarchie de vérité.

---

## 🔓 MANDAT CEO — NO-LIMIT (2026-08-10)

> **Søn (CEO)** : mandat NO-LIMIT actif — le système enchaîne sans validation intermédiaire,
> invente, optimise, protège le capital (R10 seul garde-fou).
>
> - **Doctrine** : R1-AGIR plein pouvoir · R2 additif pur · R6 fail-open · R9 audit JSON · R10 zéro ordre réel
> - **HEAD 1401/1401 verts** sur `feat/hermes-night`, base `feat/v10-c20-healthy` mergée

---

## ✅ H-LIVE-REPORT — Rapport de session live 6 sections (2026-08-10, Hermes)

`scripts/run_live_session_report.py` → `reports/live_session_<ts>.json` — **C22**

6 sections (R6 fail-open sur chacune) :
1. **top 3 paires par force delta 24h** (forces_snapshots, epoch secondes)
2. **signal_level par paire/TF** (A1/A2/A3/NONE) via `SignalGeneratorLive`
3. **pre_wave_phase** (COMPRESSION/DIVERGENCE/NEUTRAL) via `detect_pre_wave`
4. **health_score** via `run_live_health_check.build_health`
5. **dernier trade shadow + WR rolling 20** depuis `paper_trades`
6. **timestamp + version C22**

R9 JSON horodaté | R10 lecture seule. 12 tests verts.

---

## ✅ H-REPLAY-C21 — Validation replay C21 (2026-08-10, Hermes)

`scripts/run_replay_c21_validation.py` → `reports/replay_c21_validation_2026_08_10.json`

- **Paires** : EURUSD, USDCAD, USDCHF | **TF** : M15 | **Session** : LONDON | **limit** : 800
- **Métriques** : WR, PF, Sharpe + **breakdown pre_wave_phase** (COMPRESSION/DIVERGENCE/NEUTRAL — WR/PF/PnL par phase)
- **Auto-audit P5** (WR<0.75, sharpe<2.5, n>=100) | R9 honnête | R10 compute only
- Réutilise le monkeypatch `_load_bars` (bug C10 : real_volume/ohlcv inexistantes) — R2 additif, 0 core modifié
- 9 tests verts

---

## ✅ H7/H8/H9 + H-NEXT + P0 + H-EXPORTS (2026-08-10, base mergée)

| Phase | Contenu | Statut |
|---|---|---|
| H7 | `v10_fatman_wave_predictor` — détecteur pré-vague (compression sigma) | ✅ ZCode API |
| H8 | `run_replay_quality_gate` — gate M15 (EURUSD+USDCAD) | ✅ |
| H9 | WFA 5 fenêtres sur gate | ✅ |
| H-NEXT | Pre-wave branché `v10_live_pipeline` (R2 additif, R6 fail-open) | ✅ |
| P0 | Fix import `signal_7_pre_wave` replay engine | ✅ |
| H-EXPORTS | Export `v10_rl_promotion` + tests init exports | ✅ |

---

## ✅ S25-OMEGA — Nouveau cerveau central (héritage)

- **`ErrorLearner`** : apprentissage erreurs + UCB1 + forgetting
- **`AutoRecalibrator`** : recalibration auto Sharpe-aware + Regime-aware
- **`SignalScorer`** : scoring Bayesian + Volatility-regime
- **`MetaOptimizer`** : cerveau central
- **Promotion LIVE** : circuit-breaker ✅ · live_gate ✅ · paper2live ✅ · monitor temps réel ✅ · playbook CEO ✅

---

## 📊 État tests courant

- **1401/1401 tests V10 verts** (`tests/test_v10_*.py`) sur `feat/hermes-night` (HEAD `99159b9`)
- Baselines historiques : 1380 (H7-H9 base mergée) → 1395 (H-LIVE-REPORT) → 1401 (H-REPLAY-C21)
- Ruff : 0 erreur nouvelle sur fichiers modifiés (UP006/UP035/UP045 pré-existants = convention repo)

---

## 🔑 Pièges techniques récents

- **`forces_snapshots.bar_time` = epoch secondes** (pas ms) — cutoff `int(now - hours*3600)`
- **SQLite `mode=ro` crée un fichier vide** pour un chemin inexistant → `Path.exists()` explicite d'abord
- **ReplayEngine C10** : bug `_load_bars` (real_volume/ohlcv) → monkeypatch runtime requis (R2 additif)
- **Script standalone → `sys.path` ROOT** : `run_replay_c21_validation.py` importait `core.v10` sans
  `sys.path.insert(ROOT)` → `No module named 'core'` (fix 6dc5914, R2 additif)

---

## 🧭 Audit cohérence — modules orphelins (2026-08-10, Hermes)

Graphe d'imports `ast` sur `core/scripts/tests` (130 modules `core/v10`), **121 référencés**,
**9 orphelins** (aucune référence code+string+skill+cron) :

| Module | Nature | Verdict |
|---|---|---|
| `v10_pnl_simulator` | CYCLE 5 PnL simulator | Orphelin — documenté |
| `v10_trail_stop` | Cycle 17 trailing stop | Orphelin — documenté |
| `v10_master_orchestrator` | Cycle 20 orchestrateur final | Orphelin — documenté |
| `v10_cycle11_optimizer` | Cycle 11 postprocess | Orphelin — documenté |
| `v10_cycle11_planner` | Cycle 11 live-readiness | Orphelin — documenté |
| `v10_cycle12_optimizer` | Cycle 12 postprocess | Orphelin — documenté |
| `v10_cycle13_optimizer` | Cycle 13 postprocess | Orphelin — documenté |
| `v10_cycle14_optimizer` | Cycle 14 orchestrateur | Orphelin — documenté |

> **Note honnête (R9)** : `v10_learning_loop` est utilisé par `v10_daily_bilan.py`/`v10_night_summary.py`
> (via fichiers JSON reports/), PAS importé comme module → classé "orphelin" par le graphe d'imports
> pur mais opérationnel en pratique.
>
> **Décision** : ne PAS câbler les 8 orphelins en un seul coup (risque de déstabiliser les 1401 tests —
> R2 additif strict). Documentés ici pour un futur round de câblage ciblé. Méthode reproductible dans
> skill `powerflow-v10-autopilot-loop` (section audit cohérence).
