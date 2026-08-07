# PIPELINE_MAP.md — Architecture Pipeline V10

> **Référence architecte** (2026-08-07) — Vision 1-page du pipeline complet.
> Lecture rapide avant démarrage session. Détail dans `SOUL.md`.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        POWERFLOW V10 — PIPELINE UNIFIÉ                       │
│                      feat/v9-foundation-clean | 2026-08-07                  │
└──────────────────────────────────────────────────────────────────────────────┘

SOURCE DE DONNÉES
  data/v9_forces.db ──► 41 050 signaux/5min (lecture seule V10, R9)
  port 31685 ──────────► capture_server V9 (PID 5128, conservé)
  IBKR REST API ───────► Phase 184 (futur)

                              │
                              ▼  [stale gate : données > 300s → NONE forcé]

COUCHE 1 — PERCEPTION (8 modules en parallèle, chaque tick)
  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
  │ L1 Fatman   │ │ L2 Fractal  │ │ L3 SMC/BOS  │ │ L4 HMM      │
  │ Bible       │ │ 7-TF        │ │ OB/FVG      │ │ Regime      │
  │ poids: 0.35 │ │ poids: 0.20 │ │ poids: 0.15 │ │ poids: 0.10 │
  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
         │               │               │               │
  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
  │ L5 Wyckoff  │ │ L6 Behavior │ │ L7 ICT OTE  │ │ L8 Sigma    │
  │ Phase       │ │ Registry    │ │ Kill Zones  │ │ Oracle      │
  │ poids: 0.05 │ │ poids: 0.05 │ │ poids: 0.05 │ │ poids: 0.10 │
  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
         │               │               │               │
         └───────────────┴───────────────┴───────────────┘
                                  │ scores normalisés [0,1]
                                  ▼

COUCHE 2 — FATMAN INTELLIGENCE HUB (Sprint 15)
  v10_fatman_intelligence_hub.py
  • Fusion pondérée normalisée (Σ poids = 1.0 après fail-open)
  • HubVerdict : signal + level + confidence + CoT R5 + dominant_edge
  • SHAP values → dominant_edge = module SHAP le plus élevé
  • A1 (≥0.65) | A2 (0.50-0.65) | A3 (0.35-0.50) | NONE (<0.35)

                                  │
                      ┌───────────┴──────────┐
                      │ (synchrone)          │ (async post-clôture)
                      ▼                      ▼

COUCHE 3A — DÉCISION              COUCHE 5 — APPRENTISSAGE
  EdgeSelector                      LearningContinuum
  (WR≥0.50, n≥30)                   │
       │                            ├── RL Adapter 8-arms
       ▼                            │   Thompson Bandit
  RiskShield (R10)                  │   reward = pips × dir
  DD max 10%                        │   ADWIN river par arm
  Position max 2%                   │
  Levier max 5x                     ├── Bayesian Recalibrator
       │                            │   Optuna (hebdo lundi)
       ▼                            │   → thresholds JSON
                                    │
  SIGNAL ÉMIS si A1/A2              ├── Behavior Registry
  → Telegram + log R9               │   INSERT pattern
                                    │
                                    └── Error Learner
COUCHE 4 — EXÉCUTION                   ruptures changepoint
  SHADOW (obligatoire)                   → alerte si drift
  → PAPER (gate 100 trades)
  → LIVE (CEO gate + R10)
  → IBKR REST API (Phase 184)

                                  │
                                  ▼

COUCHE 6 — MESURE & RAPPORT
  Alpha metrics (WR, Sharpe, DD, pips réels)
  Dashboard Plotly live (Phase 185)
  Rapport CEO 06:00 UTC (Telegram auto)
  STATE.md + DECISIONS_LOG.md (R9 audit)
```

---

## Latences cibles

| Étape | Cible | Actuel (2026-08-06) |
|---|---|---|
| Snapshot capture | < 300ms | 57ms ✅ |
| Couche 1 perception (8 modules) | < 500ms | TBD |
| Couche 2 Hub fusion | < 100ms | TBD Sprint 15 |
| Signal → Telegram | < 2s total | TBD |
| Calibration Bayesian Optuna | < 60s (hebdo) | TBD Sprint 15 |
| RL Adapter update (1 trade) | < 5ms | TBD Sprint 15 |

---

## Points de défaillance et fail-open (R6)

| Module | Comportement si indisponible | Impact Hub |
|---|---|---|
| Fatman Bible | Exception → score = 0.50 (neutre) | Poids redistribués |
| Fractal 7-TF | score = 0.50 | Poids redistribués |
| SMC | skip silencieux | Poids redistribués |
| HMM Regime | régime = INDECISION | Poids redistribués |
| Sigma Oracle | sigma normal (RANGING par défaut) | Poids redistribués |
| Tous modules critiques L1+L2 | NONE forcé | Signal annulé |

---

## Rituels de vérification session (rappel AGENTS.md)

```bash
git pull && pytest tests/ -q          # Base saine — obligatoire
python scripts/v9_calibration.py --analyze   # Marché ouvert
python scripts/v9_dashboard.py --watch decisions --once  # KPIs
```

---

*Voir aussi : `SOUL.md` (détail complet) | `LEVIER_HUB.md` (carte leviers) | `AGENTS.md` (doctrine)*
