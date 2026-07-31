"""kill_switches.py — Chargeur central des kill switches V9.

Lit `config/v9_kill_switches.env` et expose les valeurs via des fonctions
pures. Utilisé par tous les modules qui ont besoin de connaître l'état
des switches (orchestrator, principle_engine, shadow_evaluator, etc.).

Avant : chaque module lisait `os.environ.get("V9_xxx", "0")` — mais personne
ne chargeait le fichier `.env` dans l'environnement au runtime. Les switches
n'étaient effectifs que dans les tests (conftest).

Doctrine : R6 (ne jamais lever), R18 (zéro LLM), R25' (OFF par défaut).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT / "config" / "v9_kill_switches.env"

# Cache process-local (lu une seule fois)
_switches: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _switches
    if _switches is not None:
        return _switches
    _switches = {}
    if not ENV_PATH.exists():
        return _switches
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        _switches[key.strip()] = val.strip()
    return _switches


def get(key: str, default: str = "0") -> str:
    """Retourne la valeur d'un kill switch.
    Priorité : variable d'environnement > fichier > défaut.
    """
    env_val = os.environ.get(key)
    if env_val is not None:
        return env_val
    return _load().get(key, default)


def is_enabled(key: str) -> bool:
    """Retourne True si le kill switch est activé (=="1")."""
    return get(key) == "1"


# ── Switches nommés ────────────────────────────────────────────────
def shadow_mode_enabled() -> bool:
    return is_enabled("V9_SHADOW_MODE_ENABLED")


def adaptive_thresholds_wired_enabled() -> bool:
    return is_enabled("V9_ADAPTIVE_THRESHOLDS_WIRED_ENABLED")


def trader_mini_enabled() -> bool:
    return is_enabled("V9_TRADER_MINI_ENABLED")


def auto_calibrator_enabled() -> bool:
    return is_enabled("V9_AUTO_CALIBRATOR_ENABLED")


def execution_enabled() -> bool:
    return is_enabled("V9_EXECUTION_ENABLED")


def auto_resolve_enabled() -> bool:
    return is_enabled("V9_AUTO_RESOLVE_ENABLED")


def arbiter_scorer_enabled() -> bool:
    return is_enabled("V9_ARBITER_SCORER_ENABLED")


def hitl_branching_enabled() -> bool:
    return is_enabled("V9_HITL_BRANCHING_ENABLED")


def regime_gate_enabled() -> bool:
    """Kill switch V9_REGIME_GATE_ENABLED (défaut '0' = OFF).

    Chantier A (2026-07-18) : quand OFF, le gate régime de
    l'exploitabilité est passthrough (aucun blocage) — zéro régression.
    """
    return is_enabled("V9_REGIME_GATE_ENABLED")


def kelly_cvar_enabled() -> bool:
    """Kill switch V9_KELLY_CVAR_ENABLED (défaut '0' = OFF).

    Chantier B (2026-07-18) : quand OFF, le plafond CVaR sur le sizing
    Kelly existant est inactif — sizing inchangé, zéro régression.
    """
    return is_enabled("V9_KELLY_CVAR_ENABLED")


def cvd_enabled() -> bool:
    """Kill switch V9_CVD_ENABLED (défaut '0' = OFF).

    Chantier C (2026-07-18) : quand OFF, le CVD (Cumulative Volume Delta) n'est
    pas exposé dans la scène (cvd_cumul / cvd_divergence). La couche forces
    reste passive (parse ce que l'EA envoie, ou NULL). Zéro régression.
    """
    return is_enabled("V9_CVD_ENABLED")


def loop_breaker_enabled() -> bool:
    """Kill switch V9_LOOP_BREAKER_ENABLED — garde-fou anti-boucle re-entry.

    Câblage P0.4 (2026-07-19) : source de vérité = fichier `.env` (via get()),
    pas `os.environ` seul. Le cron paper-trade lançait le supervisor sans
    charger le `.env` → le switch était lu OFF alors que le fichier dit ON.
    """
    return is_enabled("V9_LOOP_BREAKER_ENABLED")


def live_watchdog_enabled() -> bool:
    """Kill switch V9_LIVE_WATCHDOG_ENABLED — watchdog live edgefund (Axe 6).

    Défaut OFF tant que pas d'activation explicite dans le `.env`. Activé
    2026-07-19 (motion CEO « Construis le watchdog » = mandat runtime).
    """
    return is_enabled("V9_LIVE_WATCHDOG_ENABLED")


def bayesian_calibrator_enabled() -> bool:
    """Kill switch V9_BAYESIAN_CALIBRATOR_ENABLED (défaut '0' = OFF).

    Axe 1.1 J1 (2026-07-21) : quand OFF, la calibration bayésienne
    (BayesianCalibrator, `signal_generator.calibrate_confidence`) n'est pas
    consommée par le pipeline — la confiance déclarée reste inchangée, zéro
    régression. Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_BAYESIAN_CALIBRATOR_ENABLED")


def kelly_fractional_enabled() -> bool:
    """Kill switch V9_KELLY_FRACTIONAL_ENABLED (défaut '0' = OFF).

    Axe 1.2 J2 (2026-07-21) : quand OFF, le multiplicateur Kelly bayésien-borné
    (`v9_kelly_sizing.KellySizingEngine`) n'est PAS appliqué au sizing du
    trade_engine — la composition `base × dynamic_risk × kelly` dégénère en
    `base × dynamic_risk` (kelly=1.0 neutre), zéro régression. Composition
    multiplicative avec le DynamicRiskManager (jamais un remplacement).
    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_KELLY_FRACTIONAL_ENABLED")


def bayesian_predictor_enabled() -> bool:
    """Kill switch V9_BAYESIAN_PREDICTOR_ENABLED (défaut '0' = OFF).

    Axe 2.3 J5 (2026-07-21) : active le câblage du prédicteur bayésien
    (`v9_bayesian_predictor.predict()`) dans le pipeline live.
    Quand OFF, le prédicteur reste **invoquable manuellement** (CLI, scripts,
    tests) mais **NON câblé** dans `signal_generator` / `trade_engine`.
    Zéro régression : la confiance déclarée reste la source de vérité.

    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_BAYESIAN_PREDICTOR_ENABLED")


def drawdown_protector_enabled() -> bool:
    """Kill switch V9_DRAWDOWN_PROTECTOR_ENABLED (défaut '0' = OFF).

    Axe 3.2 J11 (2026-07-21) : active le câblage du Drawdown Protector
    (`v9_drawdown_protector.DrawdownProtector`) dans le pipeline live.
    Implémente 5 paliers de protection (volatility targeting, DD circuit
    breaker, recovery mode, Kelly adaptive, hedging).

    Quand OFF, le module reste invocable manuellement (CLI/scripts/tests)
    mais **NON câblé** dans `trade_engine`. Zéro régression.

    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_DRAWDOWN_PROTECTOR_ENABLED")


def risk_parity_enabled() -> bool:
    """Kill switch V9_RISK_PARITY_ENABLED (défaut '0' = OFF).

    Axe 3.3 J12 (2026-07-21) : active le câblage du Risk Parity
    (`v9_risk_parity.RiskParityEngine`) pour allocation risque-budget
    proportionnelle à la variance (standard AQR / Bridgewater) sur 5 paires
    actives (USDCAD blacklisté).

    Quand OFF, le module reste invocable manuellement mais **NON câblé**.
    Zéro régression.

    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_RISK_PARITY_ENABLED")


def cycle_memory_enabled() -> bool:
    """Kill switch V9_CYCLE_MEMORY_ENABLED (défaut '0' = OFF).

    Axe 4 J14 (2026-07-21) : active le câblage de la mémoire inter-cycles
    (`v9_cycle_memory.CycleMemory`) dans le pipeline live. Permet au
    système de rappeler les patterns historiques des décisions résolues
    par contexte opérationnel (symbol, timeframe, regime, phase, vol_bucket).

    Quand OFF, le module reste invocable manuellement mais **NON câblé**.
    Zéro régression.

    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_CYCLE_MEMORY_ENABLED")


def meta_strategy_optimizer_enabled() -> bool:
    """Kill switch V9_META_STRATEGY_OPTIMIZER_ENABLED (défaut '0' = OFF,
    actuellement **ON** par motion CEO 04h58 du 2026-07-21).

    Axe 4 J15 (2026-07-21) : active le câblage du méta-strategy optimizer
    (`v9_meta_strategy_optimizer.MetaStrategyOptimizer`) — couche au-dessus
    du StrategySelector qui re-balance les stratégies par contexte.

    Quand OFF, le meta_strategy_optimizer ne tourne PAS et le
    StrategySelector standard prend le relais. Zéro régression.
    """
    return is_enabled("V9_META_STRATEGY_OPTIMIZER_ENABLED")


def learn_loop_enabled() -> bool:
    """Kill switch V9_LEARN_LOOP_ENABLED (défaut '0' = OFF, actuellement **ON**
    par motion CEO antérieure).

    Axe 4 J16 (2026-07-21) : active la boucle d'apprentissage continue
    (`v9_learn_loop`) — orchestration ingestion décisions résolues +
    fit Platt + walk-forward + mise à jour state.

    Quand OFF, la boucle ne tourne PAS ; les décisions sont toujours
    résolues mais le système n'apprend pas de l'historique. Zéro régression.

    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_LEARN_LOOP_ENABLED")


def cross_pair_metrics_enabled() -> bool:
    """Kill switch V9_CROSS_PAIR_METRICS_ENABLED (défaut '0' = OFF).

    Axe 4 J17-J18 (2026-07-21) : active le câblage des métriques cross-pair
    (`v9_cross_pair_metrics`) — cross_pair_dispersion, pair_force_ratio,
    neutre_rate_24h. Utilisé par le regime_detector (motion CEO #8 audit
    Opus) et le watchdog live.

    Quand OFF, les métriques sont désactivées et le regime_detector
    retombe sur le mode basique. Zéro régression.

    Promotion ACTIVE = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_CROSS_PAIR_METRICS_ENABLED")


def walk_forward_enabled() -> bool:
    """Kill switch V9_WALK_FORWARD_ENABLED (défaut '0' = OFF).

    Axe 1.3 J3 (2026-07-21) : active la validation walk-forward anchored en
    mode shadow dans le pipeline live. Le walk-forward reste **toujours** un
    outil de diagnostic lecture seule (le module `walk_forward.py` ne fait
    aucun write sur la calibration live) — le kill switch contrôle
    uniquement son déclenchement automatique par le cron `V9_WalkForward`.

    Sans kill switch ON : le module est invocable manuellement via
    `scripts/v9_walk_forward.py` (CLI), ce qui produit un rapport Markdown
    dans docs/reports/. Le cron quotidien NE tourne PAS (R25' strict).

    Promotion cron AUTO = motion CEO séparée (R25' strict).
    """
    return is_enabled("V9_WALK_FORWARD_ENABLED")


def paper_trade_halt_enabled() -> bool:
    """Kill switch V9_PAPER_TRADE_HALT — HALT TOTAL du paper-trading (R6 fail-safe).

    Défaut OFF. Quand ON, le moteur de paper-trade ne doit rien ouvrir.
    C'est l'action de niveau P0 recommandée par le watchdog critique
    (remplace l'ancienne reco `V9_GBPUSD_LONG_ONLY=0` qui ré-autorisait
    les shorts au lieu d'arrêter — cf. audit edgefund 2026-07-19).
    """
    return is_enabled("V9_PAPER_TRADE_HALT")


# ──────────────────────────────────────────────────────────────────────────────
# Nouveaux kill switches (2026-07-25) — Unified Meta-Learning & Sizing
# ──────────────────────────────────────────────────────────────────────────────

def meta_learning_enabled() -> bool:
    """Kill switch V9_META_LEARNING_ENABLED — Orchestrateur unique meta-learning.

    Remplace les 4 crons séparés (auto_calibrator, auto_optimizer, learn_loop,
    walk_forward) par un cycle unifié avec état partagé et gatings croisés.
    Défaut ON (motion CEO 2026-07-25).
    """
    return is_enabled("V9_META_LEARNING_ENABLED")


def unified_sizing_enabled() -> bool:
    """Kill switch V9_UNIFIED_SIZING_ENABLED — Moteur de sizing unifié.

    Composition multiplicative cohérente : base × portfolio_risk × dd_protector
    × risk_parity × kelly × meta_strategy. Bornes finales [0.1, 3.0].
    OFF par défaut pour migration progressive (R25' strict).
    """
    return is_enabled("V9_UNIFIED_SIZING_ENABLED")


def edge_decay_monitor_enabled() -> bool:
    """Kill switch V9_EDGE_DECAY_MONITOR_ENABLED — Surveillance dégradation edge.

    Détection proactive dégradation edge par principe × session × régime.
    Auto-actions : blacklist, démotion, observation mode.
    Défaut ON (motion CEO 2026-07-25).
    """
    return is_enabled("V9_EDGE_DECAY_MONITOR_ENABLED")


def anti_serie_perdante_enabled() -> bool:
    """Kill switch V9_ANTI_SERIE_PERDANTE_ENABLED — Filtre anti-série perdante J2.

    Bloque un trade si 3 paper_trades consécutifs sur (symbol, direction)
    sont tousperdants. Additif (R2), R6 jamais bloquant (DB indisponible →
    skip silencieux). Défaut ON (motion CEO « GO MAX » 28/07).
    """
    # Désactivé explicitement ? défaut = ON pour autopilot CEO.
    return os.environ.get("V9_ANTI_SERIE_PERDANTE_ENABLED", "1") == "1"


def kill_dd_wr_enabled() -> bool:
    """Kill switch V9_KILL_DD_WR_ENABLED — Kill switch DD 24h + WR plancher J2.

    HALT si DD 24h < V9_KILL_DD_PIPS (défaut -100) OU si WR sur 20 derniers
    trades < V9_KILL_WR_FLOOR (défaut 0.40). Additif (R2), R6 jamais
    bloquant. Défaut ON (motion CEO « GO MAX » 28/07).
    """
    return os.environ.get("V9_KILL_DD_WR_ENABLED", "1") == "1"
